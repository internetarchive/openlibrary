"""Tests for :mod:`openlibrary.core.provider_tokens`.

The load-bearing ones are the refresh tests. Refresh rotation is destructive on
reuse -- presenting a spent refresh token revokes the patron's whole token
family -- so what matters is not that a refresh works but that a *second*
flight never presents a token the first one already spent.

Two backends, and the split between them is the point:

* :class:`~openlibrary.core.provider_tokens.DbTokenStore` is **the default and
  the one that ships**. :class:`TestStorage` and :class:`TestRefresh` drive it
  against a real SQLite database and prove the protocol: the grant is re-read
  after the lock is taken, the new pair lands in the same transaction, and a
  failure clears rather than retries. :class:`TestSingleFlightUnderConcurrency`
  proves the ``FOR UPDATE`` lock itself and needs a real Postgres, because
  SQLite has no row locks -- a threading lock substituted here would be testing
  the substitute. It skips unless ``OL_TEST_POSTGRES`` is set, which means CI
  does not run it; see that class's docstring for the two commands that do.
* :class:`~openlibrary.core.provider_tokens.CookieTokenStore` is a selectable
  backend for a demo or a database that has not had the DDL applied.
  :class:`TestCookieStorage`, :class:`TestTheCookieItself` and
  :class:`TestCookieRefresh` drive the real store through a fake browser jar
  rather than a memory stand-in, because the cookie is the artifact and a
  stand-in would have its own serialisation, size behaviour and username
  handling.

:class:`TestWhatTheCookieBackendCannotDo` is a characterisation test. It pins
the single-flight race **as a property of that one backend**, which is no
longer the default -- the shipped store does not have it, and
:class:`TestSingleFlightUnderConcurrency` is where that is proved.
"""

import datetime
import json
import os
import re
import threading
from typing import Final
from unittest import mock

import pytest
import web

from openlibrary.accounts import model as accounts_model
from openlibrary.core import db as db_module
from openlibrary.core import provider_tokens as pt
from openlibrary.core.provider_tokens import (
    COOKIE_NAME,
    EXPIRY_SKEW,
    CookieTokenStore,
    DbTokenStore,
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

# The Postgres copy. Read by two things that are not this file, so it is a
# published constant rather than a local detail:
#
#   * ArchiveLabs/lenny `tests/e2e/ol_half.py` parses it out of this module by
#     AST and executes it against the throwaway database in its end-to-end run.
#   * `TestTheShippedSchemaHasTheTable` below compares it against
#     `openlibrary/core/schema.sql`, which is where a fresh install gets the
#     table from.
#
# This one is the copy that has actually been executed, which is why schema.sql
# was written from it rather than the other way round.
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

SCHEMA_SQL = os.path.join(os.path.dirname(pt.__file__), "schema.sql")


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


class FakeBrowser:
    """One browser's cookie jar, wired to the real ``web.cookies``/``setcookie``.

    Everything the store does -- encrypt, serialise, size-check, set attributes
    -- runs for real; only the transport is faked.
    """

    def __init__(self, protocol: str = "http"):
        self.jar: dict[str, str] = {}
        self.attrs: dict = {}
        self.protocol = protocol

    def cookies(self):
        return web.storage(self.jar)

    def setcookie(self, name, value, expires=None, **kwargs):
        self.attrs = {"expires": expires, **kwargs}
        if not value or expires == -1:
            self.jar.pop(name, None)
        else:
            self.jar[name] = value

    def install(self, monkeypatch):
        monkeypatch.setattr(web, "cookies", self.cookies)
        monkeypatch.setattr(web, "setcookie", self.setcookie)
        monkeypatch.setattr(web, "ctx", web.storage(protocol=self.protocol), raising=False)
        return self


@pytest.fixture(autouse=True)
def _secret_key():
    """The Fernet secret the S3 keys already use (``accounts/model.py:86-90``)."""
    with mock.patch.object(accounts_model, "get_secret_key", return_value="test-secret-key"):
        yield


@pytest.fixture(autouse=True)
def _restore_the_default_store():
    """Put the module-level store back after every test.

    ``set_store`` is global, so a cookie test that did not clean up would leave
    every later database test reading a cookie jar that is not there -- and
    `get_providers` would answer `[]` rather than raising, which reads as a
    passing assertion about an empty table.
    """
    previous = pt.get_store()
    yield
    pt.set_store(previous)


@pytest.fixture
def token_db():
    """A real SQLite database with the table, under the default (db) store."""
    pt.set_store(DbTokenStore())
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db_module._get_db.cache_clear()
    database = db_module.get_db()
    database.query(PROVIDER_TOKENS_DDL)
    yield database
    database.query("DROP TABLE provider_tokens;")
    db_module._get_db.cache_clear()


@pytest.fixture
def cookie_store():
    """Swap the cookie backend in for the tests that are about the cookie."""
    pt.set_store(CookieTokenStore())


@pytest.fixture
def browser(monkeypatch, cookie_store):
    return FakeBrowser().install(monkeypatch)


class TestTheShippedSchemaHasTheTable:
    """A fresh install must get ``provider_tokens`` from ``schema.sql``.

    Before this, the table existed only as :data:`POSTGRES_DDL` in this file --
    a fixture-only table that 109 green tests were built on while the flow died
    on the last hop against a database that had never heard of it. These two
    assertions are what stops that from being true again, and they run in every
    suite with no database and no network.
    """

    @staticmethod
    def _declared_in_schema_sql() -> str:
        with open(SCHEMA_SQL) as handle:
            text = handle.read()
        match = re.search(r"^CREATE TABLE provider_tokens \(.*?^\);", text, re.DOTALL | re.MULTILINE)
        assert match, f"no `CREATE TABLE provider_tokens` in {SCHEMA_SQL}"
        return match.group(0)

    @staticmethod
    def _normalised(ddl: str) -> str:
        """Whitespace-insensitive, so indentation is not a test failure."""
        return re.sub(r"\s+", " ", ddl).strip()

    def test_schema_sql_declares_the_table(self):
        assert "provider_tokens" in self._declared_in_schema_sql()

    def test_it_is_the_same_table_the_tests_execute(self):
        """The copy in ``schema.sql`` has never been run; this one has.

        Two copies of a DDL drift silently and in the worst possible direction:
        the tests keep passing against the shape they created, while a fresh
        install gets a different table. Comparing them is one assertion and it
        is the only thing connecting the two.
        """
        assert self._normalised(self._declared_in_schema_sql()) == self._normalised(POSTGRES_DDL)

    def test_the_unique_constraint_upsert_needs_is_declared(self):
        """``upsert`` is ``ON CONFLICT (username, provider_name) DO UPDATE``.

        Without this constraint that statement does not merely behave
        differently -- Postgres rejects it outright, so the first repeat borrow
        by any patron is a 500. Named separately from the equality above so the
        failure says *which* property went, not just "the DDL changed".
        """
        assert "UNIQUE (username, provider_name)" in self._declared_in_schema_sql()


class TestStorage:
    """The shipped backend: rows in ``provider_tokens``."""

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

    def test_deleting_a_grant_that_is_not_there_changes_nothing(self, token_db):
        ProviderToken.upsert("patron", "lenny", live_grant())

        assert ProviderToken.delete("patron", "otherlib") == 0
        assert ProviderToken.get_providers("patron") == ["lenny"]

    def test_delete_all_by_username(self, token_db):
        ProviderToken.upsert("patron", "lenny", live_grant())
        ProviderToken.upsert("patron", "otherlib", live_grant())
        ProviderToken.upsert("other-patron", "lenny", live_grant())

        assert ProviderToken.delete_all_by_username("patron") == 2
        assert ProviderToken.get_providers("patron") == []
        assert ProviderToken.get_providers("other-patron") == ["lenny"]

    def test_the_default_store_is_the_table_not_the_cookie(self):
        """The whole point of this change, asserted where it can be seen.

        It takes no fixture on purpose: it reads the module's import-time
        default rather than anything a fixture installed. If a later commit
        swaps the demo backend back in, this is what says so.
        """
        assert isinstance(pt.get_store(), DbTokenStore)


class TestGrant:
    def test_repr_redacts_both_tokens(self):
        text = repr(Grant("secret-access", "secret-refresh", None, "borrow"))
        assert "secret-access" not in text
        assert "secret-refresh" not in text
        assert "<redacted>" in text
        # The non-secret fields survive, or the repr is useless in a traceback.
        assert "borrow" in text

    def test_repr_of_a_grant_without_a_refresh_token_says_so(self):
        assert "refresh_token=None" in repr(Grant("secret-access", None))

    def test_a_grant_with_no_stated_expiry_is_not_expired(self):
        assert Grant("at", "rt", None).is_expired() is False

    def test_expiry_skew_retires_a_token_before_the_provider_does(self):
        """A token valid when we check it and expired when the node sees it is
        a failed borrow, so it is retired a minute early.

        ``now`` is passed in rather than read: a test that takes one clock
        reading and compares it against another the code takes is green
        whenever the two happen to agree.
        """
        now = _utcnow()
        assert Grant("at", "rt", now + EXPIRY_SKEW - datetime.timedelta(seconds=1)).is_expired(now) is True
        assert Grant("at", "rt", now + EXPIRY_SKEW + datetime.timedelta(seconds=1)).is_expired(now) is False


class TestRefresh:
    """Refresh against the shipped backend."""

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
        ProviderToken.upsert("patron", "otherlib", live_grant(access="still-good"))

        with pytest.raises(TokenRefreshFailed):
            ProviderToken.get_fresh("patron", "lenny", ExplodingRefresher())

        assert ProviderToken.get("patron", "lenny") is None
        assert ProviderToken.get("patron", "otherlib").access_token == "still-good"

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

    SQLite cannot host it -- no row locks -- so it is gated, which means **CI
    does not run it**: a green check on this pull request does not include these
    two tests. These are the two commands they were verified with::

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
        pt.set_store(DbTokenStore())
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


class TestCookieStorage:
    """The same storage contract, over the cookie backend."""

    def test_a_stored_grant_comes_back_intact(self, browser):
        grant = live_grant()
        ProviderToken.upsert("patron", "lenny", grant)

        stored = ProviderToken.get("patron", "lenny")
        assert stored is not None
        assert stored.access_token == "at-0"
        assert stored.refresh_token == "rt-0"
        assert stored.scope == "loans:read borrow"
        assert stored.expires == grant.expires

    def test_the_token_is_recoverable_not_a_digest(self, browser):
        ProviderToken.upsert("patron", "lenny", live_grant(access="a-real-bearer-token"))

        stored = ProviderToken.get("patron", "lenny")
        assert stored is not None
        assert stored.access_token == "a-real-bearer-token"

    def test_a_missing_grant_is_none(self, browser):
        assert ProviderToken.get("patron", "lenny") is None

    def test_a_patron_may_hold_a_grant_at_several_providers(self, browser):
        ProviderToken.upsert("patron", "lenny", live_grant(access="lenny-token"))
        ProviderToken.upsert("patron", "otherlib", live_grant(access="otherlib-token"))

        assert ProviderToken.get("patron", "lenny").access_token == "lenny-token"
        assert ProviderToken.get("patron", "otherlib").access_token == "otherlib-token"
        assert ProviderToken.get_providers("patron") == ["lenny", "otherlib"]

    def test_upsert_replaces_rather_than_accumulating(self, browser):
        ProviderToken.upsert("patron", "lenny", live_grant(access="first"))
        ProviderToken.upsert("patron", "lenny", live_grant(access="second", refresh=None))

        assert ProviderToken.get_providers("patron") == ["lenny"]
        stored = ProviderToken.get("patron", "lenny")
        assert stored.access_token == "second"
        assert stored.refresh_token is None

    def test_delete_forgets_one_provider_only(self, browser):
        ProviderToken.upsert("patron", "lenny", live_grant())
        ProviderToken.upsert("patron", "otherlib", live_grant())

        assert ProviderToken.delete("patron", "lenny") == 1
        assert ProviderToken.get("patron", "lenny") is None
        assert ProviderToken.get_providers("patron") == ["otherlib"]

    def test_deleting_a_grant_that_is_not_there_changes_nothing(self, browser):
        ProviderToken.upsert("patron", "lenny", live_grant())

        assert ProviderToken.delete("patron", "otherlib") == 0
        assert ProviderToken.get_providers("patron") == ["lenny"]

    def test_delete_all_by_username(self, browser):
        ProviderToken.upsert("patron", "lenny", live_grant())
        ProviderToken.upsert("patron", "otherlib", live_grant())

        assert ProviderToken.delete_all_by_username("patron") == 2
        assert ProviderToken.get_providers("patron") == []
        assert COOKIE_NAME not in browser.jar

    def test_clearing_the_last_grant_expires_the_cookie(self, browser):
        """Not merely an empty payload: an empty cookie that is still *set*
        keeps announcing that this patron uses provider borrowing."""
        ProviderToken.upsert("patron", "lenny", live_grant())
        ProviderToken.delete("patron", "lenny")

        assert COOKIE_NAME not in browser.jar
        assert browser.attrs["expires"] == -1


class TestTheCookieItself:
    """What is actually in the browser, as opposed to what round-trips."""

    def test_the_tokens_are_ciphertext_at_rest(self, browser):
        ProviderToken.upsert("patron", "lenny", live_grant(access="a-real-bearer-token", refresh="a-real-refresh-token"))

        raw = browser.jar[COOKIE_NAME]
        assert "a-real-bearer-token" not in raw
        assert "a-real-refresh-token" not in raw

    def test_the_provider_name_and_patron_are_ciphertext_too(self, browser):
        """Which libraries a patron borrows from is not public information, so
        the whole payload is encrypted as a unit rather than per-field."""
        ProviderToken.upsert("alice", "lenny_some_small_library", live_grant())

        raw = browser.jar[COOKIE_NAME]
        assert "lenny_some_small_library" not in raw
        assert "alice" not in raw

    def test_encryption_is_the_s3_keys_scheme(self, browser):
        """Same Fernet secret, so the payload reads with either helper."""
        ProviderToken.upsert("patron", "lenny", live_grant(access="shared-scheme"))

        raw = browser.jar[COOKIE_NAME]
        payload = json.loads(accounts_model._get_fernet().decrypt(raw.encode()).decode())
        assert payload["g"]["lenny"]["a"] == "shared-scheme"

    def test_another_patrons_cookie_reads_as_no_grants(self, browser):
        """A cookie outlives a logout. A grant belongs to whoever authorized
        it, so bob must not inherit alice's bearer token by sharing a browser."""
        ProviderToken.upsert("alice", "lenny", live_grant(access="alice-token"))

        assert ProviderToken.get("bob", "lenny") is None
        assert ProviderToken.get_providers("bob") == []

    def test_a_tampered_cookie_reads_as_no_grants(self, browser):
        ProviderToken.upsert("patron", "lenny", live_grant())
        browser.jar[COOKIE_NAME] = browser.jar[COOKIE_NAME][:-6] + "AAAAAA"

        assert ProviderToken.get_providers("patron") == []

    def test_a_cookie_from_a_rotated_secret_reads_as_no_grants(self, browser):
        """Not a crash: rotating the Fernet secret must log patrons out of
        provider borrowing, not 500 every page that reads the cookie."""
        ProviderToken.upsert("patron", "lenny", live_grant())
        with mock.patch.object(accounts_model, "get_secret_key", return_value="a-different-secret"):
            assert ProviderToken.get_providers("patron") == []

    def test_it_is_httponly_and_lax(self, browser):
        ProviderToken.upsert("patron", "lenny", live_grant())

        assert browser.attrs["httponly"] is True
        assert browser.attrs["samesite"] == "Lax"

    def test_secure_is_set_under_https(self, monkeypatch, cookie_store):
        """``testing.openlibrary.org`` is https, so the demo gets ``Secure`` there."""
        FakeBrowser(protocol="https").install(monkeypatch)
        ProviderToken.upsert("patron", "lenny", live_grant())

        assert pt._is_https() is True

    def test_secure_is_not_set_under_plain_http(self, browser):
        """An unconditional ``secure=True`` -- what the ``s3`` cookie does --
        means the browser silently drops this on ``http://localhost``, which is
        the one place the flow is demonstrated. The symptom would be a borrow
        that appears to succeed and a loans page that stays empty."""
        ProviderToken.upsert("patron", "lenny", live_grant())

        assert browser.attrs["secure"] is False

    def test_no_request_context_is_no_grants_rather_than_a_crash(self, monkeypatch, cookie_store):
        """A cron or a shell has no cookies. ``web.cookies()`` raises there."""

        def boom():
            raise AttributeError("no request context")

        monkeypatch.setattr(web, "cookies", boom)
        assert ProviderToken.get("patron", "lenny") is None

    def test_an_oversized_set_drops_the_oldest_rather_than_the_newest(self, browser, caplog):
        """A cookie over the browser's cap is discarded *whole*, which would
        throw away the grant the patron just authorized. Evicting the oldest
        keeps the newest working and says so in the log."""
        # Sized so one grant fits comfortably and three do not, which is the
        # case the eviction exists for. A grant too big to store on its own is
        # a different failure, covered below.
        big = "x" * 600
        ProviderToken.upsert("patron", "first", live_grant(access=big, refresh=big))
        ProviderToken.upsert("patron", "second", live_grant(access=big, refresh=big))
        ProviderToken.upsert("patron", "third", live_grant(access=big, refresh=big))

        providers = ProviderToken.get_providers("patron")
        assert "third" in providers, "the grant just authorized must survive"
        assert "first" not in providers, "the oldest should have been evicted"
        assert len(browser.jar[COOKIE_NAME]) <= pt.MAX_COOKIE_BYTES
        assert any("cookie full" in m for m in caplog.messages)

    def test_a_single_grant_too_large_to_store_is_an_error_not_a_shrug(self, browser, caplog):
        """The patron completed a sign-in and has nothing to show for it.
        Evicting an older grant is a trim; this is a failure, and the log has
        to be able to tell an operator which one happened."""
        enormous = "x" * 4000
        ProviderToken.upsert("patron", "lenny", live_grant(access=enormous, refresh=enormous))

        assert ProviderToken.get_providers("patron") == []
        assert COOKIE_NAME not in browser.jar
        assert any("not even one grant fits" in m for m in caplog.messages)


class TestCookieRefresh:
    """Refresh against the cookie backend."""

    def test_no_stored_grant_is_none_and_touches_no_network(self, browser):
        refresher = RecordingRefresher()
        assert ProviderToken.get_fresh("patron", "lenny", refresher) is None
        assert refresher.presented == []

    def test_a_live_grant_is_returned_without_a_refresh(self, browser):
        ProviderToken.upsert("patron", "lenny", live_grant())
        refresher = RecordingRefresher()

        grant = ProviderToken.get_fresh("patron", "lenny", refresher)

        assert grant.access_token == "at-0"
        assert refresher.presented == []

    def test_an_expired_grant_is_refreshed_and_the_new_pair_persisted(self, browser):
        ProviderToken.upsert("patron", "lenny", expired_grant())
        refresher = RecordingRefresher()

        grant = ProviderToken.get_fresh("patron", "lenny", refresher)

        assert refresher.presented == ["rt-0"]
        assert grant.access_token == "at-1"
        stored = ProviderToken.get("patron", "lenny")
        assert stored.access_token == "at-1"
        assert stored.refresh_token == "rt-1"

    def test_a_second_sequential_call_presents_the_new_token_not_the_spent_one(self, browser):
        """The sequential case the cookie *does* get right: once the first
        refresh has written back, the next request reads the new pair."""
        ProviderToken.upsert("patron", "lenny", expired_grant())
        refresher = RecordingRefresher()

        ProviderToken.get_fresh("patron", "lenny", refresher)
        ProviderToken.upsert("patron", "lenny", expired_grant(access="at-1", refresh="rt-1"))
        ProviderToken.get_fresh("patron", "lenny", refresher)

        assert refresher.presented == ["rt-0", "rt-1"]
        assert len(set(refresher.presented)) == len(refresher.presented), "a token was presented twice"

    def test_an_expired_grant_with_no_refresh_token_is_none(self, browser):
        ProviderToken.upsert("patron", "lenny", expired_grant(refresh=None))
        refresher = RecordingRefresher()

        assert ProviderToken.get_fresh("patron", "lenny", refresher) is None
        assert refresher.presented == []

    def test_a_failed_refresh_clears_the_grant(self, browser):
        ProviderToken.upsert("patron", "lenny", expired_grant())

        with pytest.raises(TokenRefreshFailed):
            ProviderToken.get_fresh("patron", "lenny", ExplodingRefresher())

        assert ProviderToken.get("patron", "lenny") is None

    def test_the_clear_survives_the_raise(self, browser):
        """The clear must be committed to the cookie before the exception
        propagates, or the caller's error page re-reads a grant that is dead at
        the node."""
        ProviderToken.upsert("patron", "lenny", expired_grant())

        with pytest.raises(TokenRefreshFailed):
            ProviderToken.get_fresh("patron", "lenny", ExplodingRefresher())

        assert COOKIE_NAME not in browser.jar

    def test_a_failed_refresh_is_not_retried(self, browser):
        """A timeout and a rejection are indistinguishable here. The node may
        have rotated the token and lost the response, in which case presenting
        it again is the precise act that destroys the family."""
        ProviderToken.upsert("patron", "lenny", expired_grant())
        refresher = ExplodingRefresher()

        with pytest.raises(TokenRefreshFailed):
            ProviderToken.get_fresh("patron", "lenny", refresher)

        assert refresher.presented == ["rt-0"]

    def test_the_original_failure_is_kept_as_the_cause(self, browser):
        ProviderToken.upsert("patron", "lenny", expired_grant())
        original = RuntimeError("the node said no")

        with pytest.raises(TokenRefreshFailed) as caught:
            ProviderToken.get_fresh("patron", "lenny", ExplodingRefresher(original))

        assert caught.value.__cause__ is original

    def test_one_provider_failing_does_not_clear_another(self, browser):
        ProviderToken.upsert("patron", "lenny", expired_grant())
        ProviderToken.upsert("patron", "otherlib", live_grant(access="still-good"))

        with pytest.raises(TokenRefreshFailed):
            ProviderToken.get_fresh("patron", "lenny", ExplodingRefresher())

        assert ProviderToken.get("patron", "lenny") is None
        assert ProviderToken.get("patron", "otherlib").access_token == "still-good"

    def test_the_refreshed_pair_is_stored_as_ciphertext(self, browser):
        ProviderToken.upsert("patron", "lenny", expired_grant())
        ProviderToken.get_fresh("patron", "lenny", RecordingRefresher())

        assert "at-1" not in browser.jar[COOKIE_NAME]
        assert "rt-1" not in browser.jar[COOKIE_NAME]


class TestWhatTheCookieBackendCannotDo:
    """The cookie backend's known limitation, pinned so it cannot spread.

    This is a characterisation test and it asserts the *broken* behaviour --
    but read what it is a statement about. It characterises
    :class:`~openlibrary.core.provider_tokens.CookieTokenStore`, which this
    test installs explicitly and which **is not the shipped default**. The
    default is :class:`~openlibrary.core.provider_tokens.DbTokenStore`, which
    does not have this limitation; :class:`TestSingleFlightUnderConcurrency` is
    where that is proved, against a real Postgres.

    Leaving it untested is how a demo-scoped trade-off quietly becomes a
    production assumption. Leaving it *unlabelled* is how it reads as one.
    """

    def test_two_concurrent_requests_present_the_same_refresh_token_twice(self, monkeypatch, cookie_store):
        """Each in-flight request carries the cookie as it was when the request
        began, so both hold ``rt-0``. The second presents a token the first has
        already spent, which is what revokes a rotating token family.

        The shipped store fixes this by locking the row for the whole exchange
        and re-reading under that lock; a cookie has nowhere to re-read from,
        because the new pair exists only in the winner's response to the other
        tab. See ``DbTokenStore.get_fresh``.
        """
        first = FakeBrowser().install(monkeypatch)
        ProviderToken.upsert("patron", "lenny", expired_grant())
        snapshot = dict(first.jar)

        refresher = RecordingRefresher()
        ProviderToken.get_fresh("patron", "lenny", refresher)

        # The patron's second tab: a separate request carrying the same cookie
        # the browser held before the first refresh completed.
        second = FakeBrowser().install(monkeypatch)
        second.jar.update(snapshot)
        ProviderToken.get_fresh("patron", "lenny", refresher)

        assert refresher.presented == ["rt-0", "rt-0"], (
            "If this now shows two distinct tokens, the cookie backend gained single-flight -- delete this test rather than relaxing it."
        )
