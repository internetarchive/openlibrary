"""Tests for :mod:`openlibrary.core.provider_tokens`.

The load-bearing ones are the refresh tests. Refresh rotation is destructive on
reuse -- presenting a spent refresh token revokes the patron's whole token
family -- so what matters is not that a refresh works but what happens to the
*second* flight.

Everything here drives the real :class:`CookieTokenStore` through a fake
browser jar, rather than a memory store standing in for it. That matters: the
cookie is the artifact that ships, and a stand-in would have its own
serialisation, its own size behaviour and its own username handling -- none of
which are the ones a patron gets.

:class:`TestWhatTheCookieCannotDo` is a characterisation test, not an
aspiration. It pins the single-flight race *as a known limitation* so that a
later durable backend has to change it on purpose.
"""

import datetime
import json
import threading
from unittest import mock

import pytest
import web

from openlibrary.accounts import model as accounts_model
from openlibrary.core import provider_tokens as pt
from openlibrary.core.provider_tokens import (
    COOKIE_NAME,
    EXPIRY_SKEW,
    CookieTokenStore,
    Grant,
    ProviderToken,
    TokenRefreshFailed,
)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def live_grant(access: str = "at-0", refresh: str | None = "rt-0") -> Grant:
    return Grant(access, refresh, _utcnow() + datetime.timedelta(hours=1), "loans:read borrow")


def expired_grant(access: str = "at-0", refresh: str | None = "rt-0") -> Grant:
    return Grant(access, refresh, _utcnow() - datetime.timedelta(minutes=5), "loans:read borrow")


class RecordingRefresher:
    """A stand-in provider that records every refresh token presented to it.

    The recording is the point: the failure this module exists to contain is a
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
def _cookie_store(monkeypatch):
    """Reset the module-level store between tests, so one test's swap cannot leak."""
    previous = pt.set_store(CookieTokenStore())
    yield
    pt.set_store(previous)


@pytest.fixture
def browser(monkeypatch):
    return FakeBrowser().install(monkeypatch)


class TestStorage:
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
        """Open Library *presents* this token; a one-way transform is useless.

        Stated as its own test because a digest is the plausible wrong move
        here, and it would still pass every "something is stored" assertion.
        """
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

    def test_secure_is_set_under_https(self, monkeypatch):
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

    def test_no_request_context_is_no_grants_rather_than_a_crash(self, monkeypatch):
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


class TestGrant:
    def test_repr_redacts_both_tokens(self):
        text = repr(Grant("secret-access", "secret-refresh", None, "borrow"))
        assert "secret-access" not in text
        assert "secret-refresh" not in text
        assert "<redacted>" in text

    def test_repr_of_a_grant_without_a_refresh_token_says_so(self):
        assert "refresh_token=None" in repr(Grant("secret-access", None))

    def test_a_grant_with_no_stated_expiry_is_not_expired(self):
        assert Grant("at", "rt", None).is_expired() is False

    def test_expiry_skew_retires_a_token_before_the_provider_does(self):
        """A token valid when we check it and expired when the node sees it is
        a failed borrow, so it is retired a minute early."""
        just_inside = _utcnow() + EXPIRY_SKEW - datetime.timedelta(seconds=5)
        assert Grant("at", "rt", just_inside).is_expired() is True


class TestRefresh:
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


class TestWhatTheCookieCannotDo:
    """The known limitation, pinned so a durable backend must change it on purpose.

    This is a characterisation test. It asserts the *broken* behaviour, because
    the alternative -- leaving it untested -- is how a demo-scoped trade-off
    quietly becomes a production assumption.
    """

    def test_two_concurrent_requests_present_the_same_refresh_token_twice(self, monkeypatch):
        """Each in-flight request carries the cookie as it was when the request
        began, so both hold ``rt-0``. The second presents a token the first has
        already spent, which is what revokes a rotating token family.

        A server-side row fixes this by locking the row for the whole exchange
        and re-reading under that lock; a cookie has nowhere to re-read from,
        because the new pair exists only in the winner's response to the other
        tab. See ``ProviderToken.get_fresh``.
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
            "If this now shows two distinct tokens, the store gained single-flight -- delete this test rather than relaxing it."
        )
