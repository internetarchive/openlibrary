"""Tests for :mod:`openlibrary.core.provider_tokens`.

The load-bearing ones are the refresh tests. Refresh rotation is destructive on
reuse -- presenting a spent refresh token revokes the patron's whole token
family -- so what matters is not that a refresh works but that a *second*
flight never presents a token the first one already spent.

Two levels, deliberately:

* Everything in :class:`TestRefresh` runs anywhere, on SQLite, and proves the
  protocol: the grant is re-read after the lock is taken, the new pair lands in
  the same transaction, and a failure clears rather than retries.
* :class:`TestSingleFlightUnderConcurrency` proves the ``FOR UPDATE`` lock
  itself and needs a real Postgres, because SQLite has no row locks -- a
  threading lock substituted here would be testing the substitute. It skips
  unless ``OL_TEST_POSTGRES`` is set; see the class docstring for how to run it.
"""

import datetime
import os
import threading
from typing import Final
from unittest import mock

import pytest
import web

from openlibrary.accounts import model as accounts_model
from openlibrary.core import db as db_module
from openlibrary.core.provider_tokens import (
    EXPIRY_SKEW,
    Grant,
    ProviderToken,
    TokenRefreshFailed,
)

# sqlite-friendly DDL. Postgres gets `serial`/`timestamp without time zone`;
# sqlite is typeless but honours the declared type for PARSE_DECLTYPES.
PROVIDER_TOKENS_DDL: Final = """
CREATE TABLE provider_tokens (
    id integer primary key,
    username text not null,
    provider_name text not null,
    access_token text not null,
    refresh_token text default null,
    expires timestamp default null,
    scope text not null default '',
    created timestamp default current_timestamp,
    updated timestamp default current_timestamp,
    UNIQUE (username, provider_name)
);
"""

POSTGRES_DDL: Final = """
CREATE TABLE provider_tokens (
    id serial primary key,
    username text not null,
    provider_name text not null,
    access_token text not null,
    refresh_token text default null,
    expires timestamp without time zone default null,
    scope text not null default '',
    created timestamp without time zone default (current_timestamp at time zone 'utc'),
    updated timestamp without time zone default (current_timestamp at time zone 'utc'),
    UNIQUE (username, provider_name)
);
"""


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def live_grant(access: str = "at-0", refresh: str | None = "rt-0") -> Grant:
    return Grant(access, refresh, _utcnow() + datetime.timedelta(hours=1), "loans:read borrow")


def expired_grant(access: str = "at-0", refresh: str | None = "rt-0") -> Grant:
    return Grant(access, refresh, _utcnow() - datetime.timedelta(minutes=5), "loans:read borrow")


class RecordingRefresher:
    """A stand-in provider that records every refresh token presented to it.

    The recording is the point: the failure this module exists to prevent is a
    token being presented twice, which is invisible in the return value.
    """

    def __init__(self, delay: float = 0.0):
        self.presented: list[str] = []
        self._lock = threading.Lock()
        self._delay = delay
        self._n = 0

    def __call__(self, refresh_token: str) -> Grant:
        with self._lock:
            self.presented.append(refresh_token)
            self._n += 1
            n = self._n
        if self._delay:
            # Widen the window a missing lock would leave open.
            threading.Event().wait(self._delay)
        return Grant(f"at-{n}", f"rt-{n}", _utcnow() + datetime.timedelta(hours=1), "loans:read borrow")


class ExplodingRefresher:
    def __init__(self, exc: Exception | None = None):
        self.presented: list[str] = []
        self._exc = exc or RuntimeError("the node said no")

    def __call__(self, refresh_token: str) -> Grant:
        self.presented.append(refresh_token)
        raise self._exc


@pytest.fixture(autouse=True)
def _secret_key():
    """The Fernet secret the S3 keys already use (``accounts/model.py:86-90``)."""
    with mock.patch.object(accounts_model, "get_secret_key", return_value="test-secret-key"):
        yield


@pytest.fixture
def token_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db_module._get_db.cache_clear()
    database = db_module.get_db()
    database.query(PROVIDER_TOKENS_DDL)
    yield database
    database.query("DROP TABLE provider_tokens;")
    db_module._get_db.cache_clear()


class TestStorage:
    def test_a_stored_grant_comes_back_intact(self, token_db):
        grant = live_grant()
        ProviderToken.upsert("patron", "lenny", grant)

        stored = ProviderToken.get("patron", "lenny")
        assert stored is not None
        assert stored.access_token == "at-0"
        assert stored.refresh_token == "rt-0"
        assert stored.scope == "loans:read borrow"
        assert stored.expires == grant.expires

    def test_the_token_is_recoverable_not_a_digest(self, token_db):
        """Open Library *presents* this token; a one-way transform is useless.

        Stated as its own test because a digest is the plausible wrong move
        here, and it would still pass every "something is stored" assertion.
        """
        ProviderToken.upsert("patron", "lenny", live_grant(access="a-real-bearer-token"))

        stored = ProviderToken.get("patron", "lenny")
        assert stored is not None
        assert stored.access_token == "a-real-bearer-token"

    def test_the_token_is_ciphertext_at_rest(self, token_db):
        ProviderToken.upsert("patron", "lenny", live_grant(access="a-real-bearer-token", refresh="a-real-refresh-token"))

        row = token_db.query("SELECT * FROM provider_tokens")[0]
        assert "a-real-bearer-token" not in row.access_token
        assert "a-real-refresh-token" not in row.refresh_token
        assert accounts_model.decrypt_token(row.access_token) == "a-real-bearer-token"

    def test_encryption_is_the_s3_keys_scheme(self, token_db):
        """Same Fernet secret, so a token written here reads with either helper."""
        ProviderToken.upsert("patron", "lenny", live_grant(access="shared-scheme"))

        row = token_db.query("SELECT * FROM provider_tokens")[0]
        assert accounts_model._get_fernet().decrypt(row.access_token.encode()).decode() == "shared-scheme"

    def test_a_missing_grant_is_none(self, token_db):
        assert ProviderToken.get("patron", "lenny") is None

    def test_a_patron_may_hold_a_grant_at_several_providers(self, token_db):
        ProviderToken.upsert("patron", "lenny", live_grant(access="lenny-token"))
        ProviderToken.upsert("patron", "otherlib", live_grant(access="otherlib-token"))

        assert ProviderToken.get("patron", "lenny").access_token == "lenny-token"
        assert ProviderToken.get("patron", "otherlib").access_token == "otherlib-token"
        assert ProviderToken.get_providers("patron") == ["lenny", "otherlib"]

    def test_grants_are_per_patron(self, token_db):
        ProviderToken.upsert("alice", "lenny", live_grant(access="alice-token"))
        ProviderToken.upsert("bob", "lenny", live_grant(access="bob-token"))

        assert ProviderToken.get("alice", "lenny").access_token == "alice-token"
        assert ProviderToken.get_providers("bob") == ["lenny"]

    def test_upsert_replaces_rather_than_accumulating(self, token_db):
        ProviderToken.upsert("patron", "lenny", live_grant(access="first"))
        ProviderToken.upsert("patron", "lenny", live_grant(access="second", refresh=None))

        assert len(list(token_db.query("SELECT * FROM provider_tokens"))) == 1
        stored = ProviderToken.get("patron", "lenny")
        assert stored.access_token == "second"
        assert stored.refresh_token is None

    def test_delete_forgets_one_provider_only(self, token_db):
        ProviderToken.upsert("patron", "lenny", live_grant())
        ProviderToken.upsert("patron", "otherlib", live_grant())

        assert ProviderToken.delete("patron", "lenny") == 1
        assert ProviderToken.get("patron", "lenny") is None
        assert ProviderToken.get_providers("patron") == ["otherlib"]

    def test_delete_all_by_username(self, token_db):
        ProviderToken.upsert("patron", "lenny", live_grant())
        ProviderToken.upsert("patron", "otherlib", live_grant())
        ProviderToken.upsert("other-patron", "lenny", live_grant())

        assert ProviderToken.delete_all_by_username("patron") == 2
        assert ProviderToken.get_providers("patron") == []
        assert ProviderToken.get_providers("other-patron") == ["lenny"]


class TestGrant:
    def test_repr_redacts_both_tokens(self):
        text = repr(Grant("secret-access", "secret-refresh", None, "borrow"))
        assert "secret-access" not in text
        assert "secret-refresh" not in text
        assert "borrow" in text

    def test_repr_of_a_grant_without_a_refresh_token_says_so(self):
        assert "refresh_token=None" in repr(Grant("secret-access", None))

    def test_a_grant_with_no_stated_expiry_is_not_expired(self):
        assert Grant("at", "rt", None).is_expired() is False

    def test_expiry_skew_retires_a_token_before_the_provider_does(self):
        now = _utcnow()
        assert Grant("at", "rt", now + EXPIRY_SKEW - datetime.timedelta(seconds=1)).is_expired(now) is True
        assert Grant("at", "rt", now + EXPIRY_SKEW + datetime.timedelta(seconds=1)).is_expired(now) is False


class TestRefresh:
    def test_no_stored_grant_is_none_and_touches_no_network(self, token_db):
        refresher = RecordingRefresher()
        assert ProviderToken.get_fresh("patron", "lenny", refresher) is None
        assert refresher.presented == []

    def test_a_live_grant_is_returned_without_a_refresh(self, token_db):
        ProviderToken.upsert("patron", "lenny", live_grant())
        refresher = RecordingRefresher()

        grant = ProviderToken.get_fresh("patron", "lenny", refresher)

        assert grant.access_token == "at-0"
        assert refresher.presented == []

    def test_an_expired_grant_is_refreshed_and_the_new_pair_persisted(self, token_db):
        ProviderToken.upsert("patron", "lenny", expired_grant())
        refresher = RecordingRefresher()

        grant = ProviderToken.get_fresh("patron", "lenny", refresher)

        assert refresher.presented == ["rt-0"]
        assert grant.access_token == "at-1"
        # The new pair is durable, not just returned: the old refresh token is
        # spent the moment the provider answers.
        stored = ProviderToken.get("patron", "lenny")
        assert stored.access_token == "at-1"
        assert stored.refresh_token == "rt-1"

    def test_a_spent_refresh_token_is_never_presented_twice(self, token_db):
        """The sequential half of single-flight: the second call re-reads.

        Two tabs are the concurrent version of this and need the row lock
        (:class:`TestSingleFlightUnderConcurrency`). This one catches the same
        defect -- deciding on a grant read before the lock was taken -- without
        needing Postgres, and it is what goes red if the freshness check inside
        the lock is dropped.
        """
        ProviderToken.upsert("patron", "lenny", expired_grant())
        refresher = RecordingRefresher()

        ProviderToken.get_fresh("patron", "lenny", refresher)
        second = ProviderToken.get_fresh("patron", "lenny", refresher)

        assert refresher.presented == ["rt-0"]
        assert second.access_token == "at-1"

    def test_an_expired_grant_with_no_refresh_token_is_none(self, token_db):
        ProviderToken.upsert("patron", "lenny", expired_grant(refresh=None))
        refresher = RecordingRefresher()

        assert ProviderToken.get_fresh("patron", "lenny", refresher) is None
        assert refresher.presented == []

    def test_a_failed_refresh_clears_the_grant(self, token_db):
        ProviderToken.upsert("patron", "lenny", expired_grant())

        with pytest.raises(TokenRefreshFailed):
            ProviderToken.get_fresh("patron", "lenny", ExplodingRefresher())

        assert ProviderToken.get("patron", "lenny") is None

    def test_the_clear_survives_the_raise(self, token_db):
        """The delete is committed, not rolled back by the exception.

        It lives inside the transaction so the row stays locked across it; if
        the transaction were allowed to unwind instead, the dead grant would
        still be sitting there for the next request to present.
        """
        ProviderToken.upsert("patron", "lenny", expired_grant())
        with pytest.raises(TokenRefreshFailed):
            ProviderToken.get_fresh("patron", "lenny", ExplodingRefresher())

        assert list(token_db.query("SELECT * FROM provider_tokens")) == []

    def test_a_failed_refresh_is_not_retried(self, token_db):
        """Clear and re-authorize, never retry.

        A retry is what turns a lost response into a destroyed grant: the
        provider may have rotated the token before the response went missing,
        so the second presentation is reuse.
        """
        ProviderToken.upsert("patron", "lenny", expired_grant())
        refresher = ExplodingRefresher()

        with pytest.raises(TokenRefreshFailed):
            ProviderToken.get_fresh("patron", "lenny", refresher)
        assert ProviderToken.get_fresh("patron", "lenny", refresher) is None

        assert refresher.presented == ["rt-0"]

    def test_the_original_failure_is_kept_as_the_cause(self, token_db):
        ProviderToken.upsert("patron", "lenny", expired_grant())
        original = RuntimeError("401 invalid_grant")

        with pytest.raises(TokenRefreshFailed) as caught:
            ProviderToken.get_fresh("patron", "lenny", ExplodingRefresher(original))

        assert caught.value.__cause__ is original

    def test_one_provider_failing_does_not_clear_another(self, token_db):
        ProviderToken.upsert("patron", "lenny", expired_grant())
        ProviderToken.upsert("patron", "otherlib", live_grant())

        with pytest.raises(TokenRefreshFailed):
            ProviderToken.get_fresh("patron", "lenny", ExplodingRefresher())

        assert ProviderToken.get("patron", "otherlib") is not None

    def test_the_refreshed_pair_is_stored_as_ciphertext(self, token_db):
        ProviderToken.upsert("patron", "lenny", expired_grant())
        ProviderToken.get_fresh("patron", "lenny", RecordingRefresher())

        row = token_db.query("SELECT * FROM provider_tokens")[0]
        assert "at-1" not in row.access_token
        assert accounts_model.decrypt_token(row.access_token) == "at-1"


POSTGRES_DSN = os.environ.get("OL_TEST_POSTGRES")


@pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="needs a real Postgres: SQLite has no FOR UPDATE, so this would test nothing. Set OL_TEST_POSTGRES=host:port:dbname:user:password",
)
class TestSingleFlightUnderConcurrency:
    """Two simultaneous refreshes must produce exactly one refresh request.

    This is the test the issue asks for, and it is worth more than the
    implementation: without the row lock both flights read the same stale row
    and both present the same refresh token, which revokes the patron's entire
    token family. The provider answers the second one with an error that names
    nothing and the patron is simply logged out.

    SQLite cannot host it -- no row locks -- so it is gated, which means CI
    does not run it. These are the two commands it was verified with::

        docker run --rm -d -p 55432:5432 -e POSTGRES_PASSWORD=ol \\
            -e POSTGRES_DB=oltest --name ol-token-test postgres:18.3

        docker run --rm --network host -v "$PWD":/openlibrary -w /openlibrary \\
            -e OL_TEST_POSTGRES=127.0.0.1:55432:oltest:postgres:ol \\
            oldev:latest python -m pytest \\
            openlibrary/tests/core/test_provider_tokens.py

    Outside Docker, ``OL_TEST_POSTGRES=localhost:55432:oltest:postgres:ol``
    with a plain ``pytest`` does the same thing.
    """

    @pytest.fixture
    def pg_db(self):
        host, port, dbname, user, password = POSTGRES_DSN.split(":")
        web.config.db_parameters = {
            "dbn": "postgres",
            "host": host,
            "port": int(port),
            "db": dbname,
            "user": user,
            "pw": password,
        }
        db_module._get_db.cache_clear()
        database = db_module.get_db()
        database.query("DROP TABLE IF EXISTS provider_tokens;")
        database.query(POSTGRES_DDL)
        yield database
        database.query("DROP TABLE IF EXISTS provider_tokens;")
        db_module._get_db.cache_clear()

    def test_two_concurrent_refreshes_present_the_token_once(self, pg_db):
        ProviderToken.upsert("patron", "lenny", expired_grant())
        refresher = RecordingRefresher(delay=0.25)
        start = threading.Barrier(2)
        results: list[Grant | None] = [None, None]
        errors: list[BaseException] = []

        def flight(slot: int) -> None:
            try:
                start.wait(timeout=10)
                results[slot] = ProviderToken.get_fresh("patron", "lenny", refresher)
            except BaseException as exc:  # noqa: BLE001 - re-raised on the main thread
                errors.append(exc)

        threads = [threading.Thread(target=flight, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert not errors, errors
        # The assertion that matters. Two entries here -- especially two
        # identical ones -- is the patron being logged out.
        assert refresher.presented == ["rt-0"]
        assert len(set(refresher.presented)) == len(refresher.presented)
        # The loser gets the winner's grant, not a stale one and not None.
        assert results[0] is not None
        assert results[1] is not None
        assert results[0].access_token == results[1].access_token == "at-1"
        assert ProviderToken.get("patron", "lenny").refresh_token == "rt-1"

    def test_a_live_grant_needs_no_serialising(self, pg_db):
        """A sanity check that the lock is not simply refusing every caller."""
        ProviderToken.upsert("patron", "lenny", live_grant())
        refresher = RecordingRefresher()
        results: list[Grant | None] = [None, None]

        def flight(slot: int) -> None:
            results[slot] = ProviderToken.get_fresh("patron", "lenny", refresher)

        threads = [threading.Thread(target=flight, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert refresher.presented == []
        assert results[0].access_token == results[1].access_token == "at-0"
