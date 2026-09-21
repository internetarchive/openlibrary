"""Tests for the Lenny borrow flow (#12844).

Weighted towards the failure paths. The happy path is one HTTP round trip and
hard to get wrong; the security of this flow lives entirely in what it
*refuses* -- a replayed callback, a code from the wrong node, a node that does
not offer S256 -- and a check nothing proves is a check that does not work.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import time
import pathlib
import urllib.parse
from typing import ClassVar

import httpx
import pytest
import web

from openlibrary.core.provider_tokens import Grant, TokenRefreshFailed
from openlibrary.plugins.upstream import lenny

NODE = {
    "issuer": "https://lennyforlibraries.org",
    "client_id": "ol-client",
    "client_secret": "s3cret",
}
OTHER_NODE_ISS = "https://lenny.example.org"

DISCOVERY = {
    "issuer": NODE["issuer"],
    "authorization_endpoint": "https://lennyforlibraries.org/v1/api/oauth2/authorize",
    "token_endpoint": "https://lennyforlibraries.org/v1/api/oauth2/token",
    "code_challenge_methods_supported": ["S256"],
    "authorization_response_iss_parameter_supported": True,
}


class FakeMemcache:
    def __init__(self):
        self.store: dict = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, expires=0):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture
def memcache(monkeypatch):
    fake = FakeMemcache()
    monkeypatch.setattr(lenny.cache, "get_memcache", lambda: fake)
    return fake


class TestPkce:
    def test_challenge_is_the_s256_of_the_verifier(self):
        """A wrong challenge is accepted by the authorize call and only fails at
        the token exchange, so it is worth pinning against the RFC directly."""
        verifier, challenge = lenny.pkce_pair()
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        assert challenge == expected

    def test_challenge_is_unpadded_base64url(self):
        _, challenge = lenny.pkce_pair()
        assert "=" not in challenge
        assert "+" not in challenge
        assert "/" not in challenge

    def test_each_call_is_unique(self):
        assert lenny.pkce_pair()[0] != lenny.pkce_pair()[0]


class TestDiscovery:
    def _resp(self, payload):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        return Resp()

    def test_reads_and_caches(self, memcache, monkeypatch):
        calls = []

        def fake_get(url, timeout=None):
            calls.append(url)
            return self._resp(DISCOVERY)

        monkeypatch.setattr(lenny.requests, "get", fake_get)
        assert lenny.discover(NODE["issuer"])["token_endpoint"] == DISCOVERY["token_endpoint"]
        lenny.discover(NODE["issuer"])
        assert len(calls) == 1, "second call should come from cache"
        assert calls[0] == "https://lennyforlibraries.org/.well-known/oauth-authorization-server"

    def test_rejects_a_node_without_s256(self, memcache, monkeypatch):
        """Fails closed. `plain` is refused by every node today, so a node
        offering it is either much older or lying."""
        monkeypatch.setattr(
            lenny.requests,
            "get",
            lambda url, timeout=None: self._resp({**DISCOVERY, "code_challenge_methods_supported": ["plain"]}),
        )
        with pytest.raises(ValueError, match="S256"):
            lenny.discover(NODE["issuer"])

    def test_rejects_a_document_missing_an_endpoint(self, memcache, monkeypatch):
        broken = {k: v for k, v in DISCOVERY.items() if k != "token_endpoint"}
        monkeypatch.setattr(lenny.requests, "get", lambda url, timeout=None: self._resp(broken))
        with pytest.raises(ValueError, match="token_endpoint"):
            lenny.discover(NODE["issuer"])

    def test_a_rejected_document_is_not_cached(self, memcache, monkeypatch):
        monkeypatch.setattr(
            lenny.requests,
            "get",
            lambda url, timeout=None: self._resp({**DISCOVERY, "code_challenge_methods_supported": []}),
        )
        with pytest.raises(ValueError, match="S256"):
            lenny.discover(NODE["issuer"])
        assert memcache.store == {}


class TestStateIsSingleUse:
    def test_a_state_can_only_be_consumed_once(self, memcache):
        """A callback replayed from browser history, or by anyone who saw the
        URL, must find nothing left to complete."""
        memcache.set(lenny._state_key("abc"), {"issuer": NODE["issuer"]})
        assert lenny.take_state("abc") is not None
        assert lenny.take_state("abc") is None

    def test_an_unknown_state_is_none(self, memcache):
        assert lenny.take_state("never-issued") is None


class TestIssuerCheck:
    """One callback path serves every node, so `state` says which node we
    expected and `iss` has to agree. Without this a hostile node can replay a
    code and have OL redeem it elsewhere -- the OAuth mix-up attack."""

    def test_matching_issuer_passes(self):
        lenny.check_issuer({"issuer": NODE["issuer"]}, NODE["issuer"])

    def test_trailing_slash_is_not_a_mismatch(self):
        lenny.check_issuer({"issuer": NODE["issuer"] + "/"}, NODE["issuer"])

    def test_a_different_node_is_refused(self):
        with pytest.raises(ValueError, match="does not match"):
            lenny.check_issuer({"issuer": NODE["issuer"]}, OTHER_NODE_ISS)

    def test_a_missing_iss_is_refused(self):
        """Every node advertises the iss parameter, so its absence is itself
        wrong -- treating it as "nothing to check" would defeat the check."""
        with pytest.raises(ValueError, match="no iss"):
            lenny.check_issuer({"issuer": NODE["issuer"]}, None)

    def test_a_prefix_of_the_issuer_is_refused(self):
        with pytest.raises(ValueError, match="does not match"):
            lenny.check_issuer({"issuer": NODE["issuer"]}, "https://lennyforlibraries.org.evil.test")


class TestBorrowErrors:
    def test_each_typed_failure_has_its_own_message(self):
        """ "All copies are out" and "you have too many out" ask the patron to do
        different things."""
        messages = {e: lenny.LennyBorrowError(e, 409).message for e in lenny.BORROW_ERRORS}
        assert len(set(messages.values())) == len(messages)

    def test_an_unknown_error_still_has_a_message(self):
        assert lenny.LennyBorrowError("something_new", 500).message

    def test_loan_limit_is_not_reported_as_unavailable(self):
        assert lenny.LennyBorrowError("loan_limit_reached", 429).message != lenny.LennyBorrowError("unavailable", 409).message


class TestNodeForEdition:
    def test_returns_none_for_an_unparsable_key(self, monkeypatch):
        monkeypatch.setattr(lenny, "nodes", lambda: {"lenny": NODE})
        assert lenny.node_for_edition("/books/not-an-olid") is None

    def test_matches_a_configured_node_by_provider_name(self, monkeypatch):
        monkeypatch.setattr(lenny, "nodes", lambda: {"lenny": NODE})
        monkeypatch.setattr(
            lenny.Acquisition,
            "get_by_edition",
            staticmethod(lambda edition_id, provider_name=None: [lenny.Acquisition(provider_name="lenny")]),
        )
        assert lenny.node_for_edition("/books/OL51008637M") == ("lenny", NODE)

    def test_ignores_an_unconfigured_lenny_node(self, monkeypatch):
        """A harvested feed does not imply credentials: a node whose operator
        never connected it to Open Library cannot be borrowed from."""
        monkeypatch.setattr(lenny, "nodes", lambda: {"lenny": NODE})
        monkeypatch.setattr(
            lenny.Acquisition,
            "get_by_edition",
            staticmethod(lambda edition_id, provider_name=None: [lenny.Acquisition(provider_name="lenny_other_org")]),
        )
        assert lenny.node_for_edition("/books/OL51008637M") is None

    def test_ignores_a_non_lenny_provider(self, monkeypatch):
        monkeypatch.setattr(lenny, "nodes", lambda: {"lenny": NODE})
        monkeypatch.setattr(
            lenny.Acquisition,
            "get_by_edition",
            staticmethod(lambda edition_id, provider_name=None: [lenny.Acquisition(provider_name="betterworldbooks")]),
        )
        assert lenny.node_for_edition("/books/OL51008637M") is None


class TestTokenExchange:
    def test_sends_the_verifier_and_returns_the_token(self, memcache, monkeypatch):
        captured = {}

        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"access_token": "at-123", "refresh_token": "rt-456", "token_type": "Bearer"}

        def fake_post(url, data=None, headers=None, timeout=None):
            captured["url"] = url
            captured["data"] = data
            return Resp()

        monkeypatch.setattr(lenny, "discover", lambda issuer: DISCOVERY)
        monkeypatch.setattr(lenny.requests, "post", fake_post)
        pending = {
            "issuer": NODE["issuer"],
            "client_id": NODE["client_id"],
            "client_secret": NODE["client_secret"],
            "code_verifier": "verifier-abc",
            "redirect_uri": "https://openlibrary.org/borrow/lenny/callback",
        }
        grant = lenny.exchange_code(pending, "code-xyz")
        assert (grant.access_token, grant.refresh_token) == ("at-123", "rt-456")
        assert captured["url"] == DISCOVERY["token_endpoint"]
        assert captured["data"]["code_verifier"] == "verifier-abc"
        assert captured["data"]["grant_type"] == "authorization_code"
        assert "refresh_token" not in captured["data"], "the code grant does not present a refresh token"

    def test_a_missing_refresh_token_is_not_an_error(self, memcache, monkeypatch):
        """A node is not obliged to issue one, and a borrow works without it."""

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"access_token": "at-only"}

        monkeypatch.setattr(lenny, "discover", lambda issuer: DISCOVERY)
        monkeypatch.setattr(lenny.requests, "post", lambda *a, **k: Resp())
        pending = {"issuer": NODE["issuer"], "code_verifier": "v", "client_id": "c", "client_secret": "s", "redirect_uri": "r"}
        grant = lenny.exchange_code(pending, "code")
        assert grant.access_token == "at-only"
        assert grant.refresh_token is None

    def test_a_response_without_a_token_raises(self, memcache, monkeypatch):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"token_type": "Bearer"}

        monkeypatch.setattr(lenny, "discover", lambda issuer: DISCOVERY)
        monkeypatch.setattr(lenny.requests, "post", lambda *a, **k: Resp())
        with pytest.raises(ValueError, match="no access_token"):
            lenny.exchange_code({"issuer": NODE["issuer"], "code_verifier": "v", "client_id": "c", "client_secret": "s", "redirect_uri": "r"}, "code")


class TestBorrowCall:
    def _pending(self):
        return {"issuer": NODE["issuer"], "provider_name": "lenny"}

    def test_posts_the_edition_id_with_a_bearer_token(self, monkeypatch):
        captured = {}

        class Resp:
            status_code = 201
            headers: ClassVar[dict] = {"content-type": "application/json"}

            def json(self):
                return {"status": "borrowed", "edition_id": 51008637, "due_at": "2026-09-24"}

        def fake_post(url, data=None, headers=None, timeout=None):
            captured.update(url=url, data=data, headers=headers)
            return Resp()

        monkeypatch.setattr(lenny.requests, "post", fake_post)
        loan = lenny.borrow(self._pending(), "at-123", 51008637)
        assert loan["status"] == "borrowed"
        assert captured["url"] == "https://lennyforlibraries.org/v1/api/oauth2/borrow"
        assert captured["data"] == {"edition_id": 51008637}
        assert captured["headers"]["Authorization"] == "Bearer at-123"

    @pytest.mark.parametrize(("status", "error"), [(404, "not_found"), (409, "unavailable"), (429, "loan_limit_reached"), (400, "not_lendable")])
    def test_typed_failures_surface_as_themselves(self, monkeypatch, status, error):
        class Resp:
            headers: ClassVar[dict] = {"content-type": "application/json"}

            def __init__(self):
                self.status_code = status

            def json(self):
                return {"error": error}

        monkeypatch.setattr(lenny.requests, "post", lambda *a, **k: Resp())
        with pytest.raises(lenny.LennyBorrowError) as excinfo:
            lenny.borrow(self._pending(), "at-123", 1)
        assert excinfo.value.error == error
        assert excinfo.value.message == lenny.BORROW_ERRORS[error]

    def test_a_non_json_failure_does_not_crash(self, monkeypatch):
        """A proxy or WAF between us and the node returns HTML, not JSON."""

        class Resp:
            status_code = 502
            headers: ClassVar[dict] = {"content-type": "text/html"}

            def json(self):
                raise ValueError("not json")

        monkeypatch.setattr(lenny.requests, "post", lambda *a, **k: Resp())
        with pytest.raises(lenny.LennyBorrowError) as excinfo:
            lenny.borrow(self._pending(), "at-123", 1)
        assert excinfo.value.error == "unknown_error"
        assert excinfo.value.message


class TestAuthorizeUrl:
    """The authorize leg's parameters are its whole security surface."""

    def _params(self, email=None):
        url = lenny.authorize_url(DISCOVERY, NODE, "state-1", "challenge-1", email)
        query = urllib.parse.urlparse(url).query
        # `keep_blank_values`, or `login_hint=` reads as absent and an empty
        # hint sent to the node looks like a test that passed.
        return dict(urllib.parse.parse_qsl(query, keep_blank_values=True))

    def test_asks_for_loans_read_alongside_borrow(self):
        """`borrow` alone creates the loan and then #13687 needs a second
        consent to read it back. Both are in the node's `scopes_supported`."""
        assert set(self._params()["scope"].split()) == {"borrow", "loans:read"}

    def test_the_scope_string_is_space_delimited(self):
        """RFC 6749 s3.3. A comma would be one unregistered scope, and an
        unregistered scope is an error at the node, not a narrowing."""
        assert "," not in lenny.SCOPES
        assert lenny.SCOPES.split() == ["loans:read", "borrow"]

    def test_login_hint_carries_the_patrons_email(self):
        assert self._params("patron@example.org")["login_hint"] == "patron@example.org"

    def test_no_login_hint_when_the_account_has_no_email(self):
        """A legacy account with no address must not send `login_hint=None`."""
        assert "login_hint" not in self._params(None)
        assert "login_hint" not in self._params("")

    def test_the_challenge_method_is_pinned_to_s256(self):
        assert self._params()["code_challenge_method"] == "S256"

    def test_carries_the_state_and_the_challenge_not_the_verifier(self):
        params = self._params()
        assert params["state"] == "state-1"
        assert params["code_challenge"] == "challenge-1"
        assert params["response_type"] == "code"


class Redirected(Exception):
    """Stands in for `web.seeother`, which needs a request context."""

    def __init__(self, url: str):
        super().__init__(url)
        self.url = url


class TestAuthorizeLeg:
    """The handler, not just `authorize_url`: what it writes to the pending
    state is what the callback and the token row are later keyed on."""

    @pytest.fixture
    def leg(self, memcache, monkeypatch):
        class FakeUser:
            key = "/people/patron"

            def get_username(self):
                return "patron"

            def get_email(self):
                return "patron@example.org"

        def seeother(url):
            raise Redirected(url)

        monkeypatch.setattr(lenny, "get_current_user", FakeUser)
        monkeypatch.setattr(lenny, "node_for_edition", lambda key: ("lenny", NODE))
        monkeypatch.setattr(lenny, "discover", lambda issuer, timeout=None: DISCOVERY)
        monkeypatch.setattr(lenny.web, "seeother", seeother)
        return memcache

    def _go(self, leg):
        with pytest.raises(Redirected) as excinfo:
            lenny.lenny_borrow().GET("OL51008637M")
        pending = next(iter(leg.store.values()))
        return excinfo.value.url, pending

    def test_the_pending_state_keys_on_the_bare_username(self, leg):
        """`ProviderToken` rows and `OpenLibraryAccount.anonymize` both key on
        the bare username. `/people/patron` would write a grant that neither
        the loan lookup nor account deletion can find."""
        _, pending = self._go(leg)
        assert pending["username"] == "patron"

    def test_the_verifier_stays_server_side(self, leg):
        """PKCE is worthless if the verifier travels with the challenge."""
        url, pending = self._go(leg)
        assert pending["code_verifier"]
        assert pending["code_verifier"] not in url

    def test_the_redirect_asks_for_both_scopes(self, leg):
        url, _ = self._go(leg)
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        assert set(params["scope"].split()) == {"borrow", "loans:read"}

    def test_the_redirect_hints_the_patrons_email(self, leg):
        url, _ = self._go(leg)
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        assert params["login_hint"] == "patron@example.org"

    def test_the_state_the_node_is_given_is_the_one_stored(self, leg):
        url, _ = self._go(leg)
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        assert lenny._state_key(params["state"]) in leg.store

    def test_a_signed_out_patron_comes_back_to_the_borrow_they_asked_for(self, leg, monkeypatch):
        """Not to the book page. Sending them there loses the click -- they
        arrive signed in, looking at the same Borrow button -- and inside the
        popup (#13688) it also leaves them on a book page 520px wide.
        """
        monkeypatch.setattr(lenny, "get_current_user", lambda: None)
        with pytest.raises(Redirected) as excinfo:
            lenny.lenny_borrow().GET("OL51008637M")
        assert excinfo.value.url == "/account/login?redirect=/borrow/lenny/OL51008637M"

    def test_a_signed_out_patron_starts_no_authorization(self, leg, monkeypatch):
        """Nothing is in flight until there is a patron to key the grant on."""
        monkeypatch.setattr(lenny, "get_current_user", lambda: None)
        with pytest.raises(Redirected):
            lenny.lenny_borrow().GET("OL51008637M")
        assert leg.store == {}


class TestGrantFromPayload:
    def test_expires_is_derived_from_expires_in(self):
        before = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        grant = lenny._grant_from_payload({"access_token": "at", "expires_in": 3600})
        assert grant.expires is not None
        delta = grant.expires - before
        assert datetime.timedelta(seconds=3599) <= delta <= datetime.timedelta(seconds=3601)

    def test_expires_is_naive_utc_to_match_the_table(self):
        """`provider_tokens` compares against a naive UTC now; an aware value
        raises TypeError at the comparison, inside a locked transaction."""
        grant = lenny._grant_from_payload({"access_token": "at", "expires_in": 3600})
        assert grant.expires.tzinfo is None
        assert grant.is_expired() is False

    def test_a_missing_expires_in_leaves_the_expiry_unset(self):
        assert lenny._grant_from_payload({"access_token": "at"}).expires is None

    def test_an_unparsable_expires_in_raises(self):
        """Not tolerated, because `Grant.is_expired` reads a missing expiry as
        "still live": swallowing this buys one borrow and pays for it later
        with a grant that is never refreshed and a logout nobody can explain."""
        with pytest.raises(ValueError, match="soon"):
            lenny._grant_from_payload({"access_token": "at", "expires_in": "soon"})

    def test_the_granted_scope_is_kept(self):
        """The node may narrow what it granted; a later loan lookup has to be
        able to see that it did."""
        payload = {"access_token": "at", "scope": "borrow"}
        assert lenny._grant_from_payload(payload).scope == "borrow"

    def test_an_absent_refresh_token_is_none_not_empty(self):
        """`ProviderToken` stores NULL for None and would encrypt "" as a real
        token, which `get_fresh` would then present to the node."""
        assert lenny._grant_from_payload({"access_token": "at"}).refresh_token is None


class TestRefresher:
    """`get_fresh` calls this with `SELECT ... FOR UPDATE` held on the patron's
    row, so anything it waits for, the row waits for."""

    def _post_resp(self, payload):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        return Resp()

    def test_both_network_calls_carry_the_refresh_timeout(self, memcache, monkeypatch):
        """Discovery counts: a cache miss inside a refresh is a second network
        call under the same lock. Without a bound here the row is held for
        whatever the node feels like."""
        timeouts = []

        def fake_get(url, timeout=None):
            timeouts.append(timeout)
            return self._post_resp(DISCOVERY)

        def fake_post(url, data=None, headers=None, timeout=None):
            timeouts.append(timeout)
            return self._post_resp({"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 3600})

        monkeypatch.setattr(lenny.requests, "get", fake_get)
        monkeypatch.setattr(lenny.requests, "post", fake_post)
        lenny.node_refresher(NODE)("rt-1")
        assert timeouts == [lenny.REFRESH_TIMEOUT_SECONDS, lenny.REFRESH_TIMEOUT_SECONDS]
        assert lenny.REFRESH_TIMEOUT_SECONDS < lenny.HTTP_TIMEOUT_SECONDS

    def test_presents_the_refresh_token_grant(self, memcache, monkeypatch):
        captured = {}

        def fake_post(url, data=None, headers=None, timeout=None):
            captured.update(data)
            return self._post_resp({"access_token": "at-2", "refresh_token": "rt-2"})

        monkeypatch.setattr(lenny, "discover", lambda issuer, timeout=None: DISCOVERY)
        monkeypatch.setattr(lenny.requests, "post", fake_post)
        grant = lenny.node_refresher(NODE)("rt-1")
        assert captured["grant_type"] == "refresh_token"
        assert captured["refresh_token"] == "rt-1"
        assert captured["client_id"] == NODE["client_id"]
        assert "code" not in captured
        assert (grant.access_token, grant.refresh_token) == ("at-2", "rt-2")

    def test_a_rejection_propagates_rather_than_being_retried(self, memcache, monkeypatch):
        """`get_fresh` deletes the grant on any exception. Swallowing one here
        would hand it a Grant built from an error body, or hide the failure
        until the node revoked the family."""

        class Resp:
            def raise_for_status(self):
                raise RuntimeError("400 invalid_grant")

            def json(self):
                return {}

        monkeypatch.setattr(lenny, "discover", lambda issuer, timeout=None: DISCOVERY)
        monkeypatch.setattr(lenny.requests, "post", lambda *a, **k: Resp())
        with pytest.raises(RuntimeError):
            lenny.node_refresher(NODE)("rt-1")


class TestAccessTokenFor:
    def test_returns_the_stored_token(self, monkeypatch):
        monkeypatch.setattr(lenny, "nodes", lambda: {"lenny": NODE})
        monkeypatch.setattr(
            lenny.ProviderToken,
            "get_fresh",
            staticmethod(lambda username, provider_name, refresher: Grant(access_token="at-9")),
        )
        assert lenny.access_token_for("patron", "lenny") == "at-9"

    def test_an_unconfigured_node_is_none(self, monkeypatch):
        """Credentials come from config; without them there is nothing to
        refresh with, so a stored grant is unusable."""
        monkeypatch.setattr(lenny, "nodes", dict)
        assert lenny.access_token_for("patron", "lenny") is None

    def test_no_stored_grant_is_none(self, monkeypatch):
        monkeypatch.setattr(lenny, "nodes", lambda: {"lenny": NODE})
        monkeypatch.setattr(lenny.ProviderToken, "get_fresh", staticmethod(lambda *a, **k: None))
        assert lenny.access_token_for("patron", "lenny") is None

    def test_a_cleared_grant_is_none_not_an_exception(self, monkeypatch):
        """`TokenRefreshFailed` means the row is already gone and the patron
        must authorize again -- the same answer as holding nothing."""

        def boom(*a, **k):
            raise TokenRefreshFailed("cleared")

        monkeypatch.setattr(lenny, "nodes", lambda: {"lenny": NODE})
        monkeypatch.setattr(lenny.ProviderToken, "get_fresh", staticmethod(boom))
        assert lenny.access_token_for("patron", "lenny") is None


class TestCallback:
    """The unit tests above prove `check_issuer` refuses. These prove the
    callback actually calls it, and calls it before spending the code."""

    @pytest.fixture
    def flow(self, memcache, monkeypatch, request_context_fixture):
        """A pending authorization, with every side effect recorded.

        ``request_context_fixture`` because both endings are now rendered
        templates, and Jinja's gettext reads the request's language.
        """
        request_context_fixture(lang="en")
        web.ctx.flash = []
        recorded: dict = {"order": [], "cookies": [], "stored": []}
        memcache.set(
            lenny._state_key("st"),
            {
                "issuer": NODE["issuer"],
                "client_id": NODE["client_id"],
                "client_secret": NODE["client_secret"],
                "code_verifier": "v",
                "redirect_uri": "https://openlibrary.org/borrow/lenny/callback",
                "edition_key": "/books/OL51008637M",
                "provider_name": "lenny",
                "username": "patron",
            },
        )

        def fake_exchange(pending, code):
            recorded["order"].append("exchange")
            return Grant(access_token="at-1", refresh_token="rt-1")

        def fake_upsert(username, provider_name, grant):
            recorded["order"].append("upsert")
            recorded["stored"].append((username, provider_name, grant.access_token, grant.refresh_token))
            return grant

        def fake_borrow(pending, token, edition_id):
            recorded["order"].append("borrow")
            recorded["token"] = token
            return {"status": "borrowed", "edition_id": edition_id, "due_at": "2026-09-24"}

        monkeypatch.setattr(lenny, "exchange_code", fake_exchange)
        monkeypatch.setattr(lenny.ProviderToken, "upsert", staticmethod(fake_upsert))
        monkeypatch.setattr(lenny, "borrow", fake_borrow)
        monkeypatch.setattr(lenny.web, "setcookie", lambda *a, **k: recorded["cookies"].append(a))
        return recorded

    def _call(self, monkeypatch, **params):
        args = {"code": "c-1", "state": "st", "iss": NODE["issuer"], "error": None}
        args.update(params)
        monkeypatch.setattr(lenny.web, "input", lambda **kw: web.storage(**args))
        return lenny.lenny_callback().GET()

    def test_a_mismatched_iss_aborts_before_the_code_is_spent(self, flow, monkeypatch):
        """The mix-up defence only works if it fires before the exchange: a
        code redeemed at the wrong node is already the damage."""
        body = self._call(monkeypatch, iss=OTHER_NODE_ISS)
        assert "could not be verified" in body.rawtext
        assert flow["order"] == []

    def test_a_missing_iss_aborts_before_the_code_is_spent(self, flow, monkeypatch):
        body = self._call(monkeypatch, iss=None)
        assert "could not be verified" in body.rawtext
        assert flow["order"] == []

    def test_a_mismatched_iss_leaves_no_grant_stored(self, flow, monkeypatch):
        self._call(monkeypatch, iss=OTHER_NODE_ISS)
        assert flow["stored"] == []

    def test_the_grant_is_stored_before_the_loan_is_created(self, flow, monkeypatch):
        """A loan made with a grant Open Library failed to keep is a live
        credential at a third-party library with no record of it here."""
        self._call(monkeypatch)
        assert flow["order"] == ["exchange", "upsert", "borrow"]
        assert flow["stored"] == [("patron", "lenny", "at-1", "rt-1")]

    def test_a_storage_failure_stops_before_the_loan(self, flow, monkeypatch):
        def boom(username, provider_name, grant):
            flow["order"].append("upsert")
            raise RuntimeError("no such table: provider_tokens")

        monkeypatch.setattr(lenny.ProviderToken, "upsert", staticmethod(boom))
        body = self._call(monkeypatch)
        assert "could not complete the loan" in body.rawtext
        assert "borrow" not in flow["order"]

    def test_no_credential_reaches_the_browser(self, flow, monkeypatch):
        """The grant lives in `provider_tokens`, not in a cookie. Nothing in
        this flow should be writing one."""
        self._call(monkeypatch)
        assert flow["cookies"] == []

    def test_the_borrow_presents_the_freshly_exchanged_token(self, flow, monkeypatch):
        self._call(monkeypatch)
        assert flow["token"] == "at-1"

    def test_a_replayed_callback_finds_nothing_in_flight(self, flow, monkeypatch):
        self._call(monkeypatch)
        flow["order"].clear()
        body = self._call(monkeypatch)
        assert "expired" in body.rawtext
        assert flow["order"] == []


NODE_B = {
    "issuer": "https://lenny-b.example.org",
    "client_id": "ol-client",
    "client_secret": "s3cret",
}


@pytest.fixture
def two_nodes(monkeypatch):
    monkeypatch.setattr(lenny, "nodes", lambda: {"lenny": NODE, "lenny_b": NODE_B})
    monkeypatch.setattr(
        lenny.ProviderToken,
        "get_providers",
        staticmethod(lambda username: ["lenny", "lenny_b"]),
    )
    monkeypatch.setattr(lenny, "access_token_for", lambda username, provider_name: f"at-{provider_name}")


class TestLoanFromNode:
    """The node speaks in bare edition integers; the page needs OL keys."""

    def test_the_bare_integer_becomes_an_edition_key(self):
        loan = lenny.loan_from_node("lenny", NODE["issuer"], "patron", {"edition_id": 37044497})
        assert loan is not None
        assert loan["book"] == "/books/OL37044497M"

    def test_a_string_edition_id_is_accepted(self):
        """Nothing in the contract promises JSON numbers rather than strings,
        and a loan dropped over that is a book the patron cannot find."""
        loan = lenny.loan_from_node("lenny", NODE["issuer"], "patron", {"edition_id": "37044497"})
        assert loan is not None
        assert loan["book"] == "/books/OL37044497M"

    def test_a_missing_edition_id_is_dropped_not_raised(self):
        assert lenny.loan_from_node("lenny", NODE["issuer"], "patron", {"due_at": None}) is None

    def test_a_nonsense_edition_id_is_dropped_not_raised(self):
        assert lenny.loan_from_node("lenny", NODE["issuer"], "patron", {"edition_id": "OL5M"}) is None

    def test_the_read_url_points_at_the_node(self):
        loan = lenny.loan_from_node("lenny", NODE["issuer"], "patron", {"edition_id": 46539165})
        assert loan is not None
        assert loan["read_url"] == "https://lennyforlibraries.org/v1/api/items/46539165/read"

    def test_borrowed_at_becomes_a_posix_timestamp(self):
        loan = lenny.loan_from_node("lenny", NODE["issuer"], "patron", {"edition_id": 1, "borrowed_at": "2026-09-20T12:00:00Z"})
        assert loan is not None
        assert loan["loaned_at"] == datetime.datetime(2026, 9, 20, 12, 0, tzinfo=datetime.UTC).timestamp()

    def test_a_naive_timestamp_is_read_as_utc(self, monkeypatch):
        """The node's rows are UTC. Reading them as the web server's local time
        would move every "Borrowed" date by the deploy's offset.

        The TZ is forced away from UTC deliberately. Without it this test
        passes against source that does no tagging at all -- the test
        container runs UTC, where a naive `.timestamp()` happens to agree, so
        the assertion never reaches the behaviour it names. Checked by
        mutation: with the `tzinfo` tagging removed, the UTC-container version
        of this test stayed green.
        """
        monkeypatch.setenv("TZ", "America/Los_Angeles")
        time.tzset()
        try:
            loan = lenny.loan_from_node("lenny", NODE["issuer"], "patron", {"edition_id": 1, "borrowed_at": "2026-09-20T12:00:00"})
        finally:
            monkeypatch.undo()
            time.tzset()
        assert loan is not None
        assert loan["loaned_at"] == datetime.datetime(2026, 9, 20, 12, 0, tzinfo=datetime.UTC).timestamp()

    def test_a_null_borrowed_at_is_zero_not_none(self):
        """`borrowed_at` is documented nullable. The loans template feeds
        `loaned_at` to `datetime_from_utc_timestamp`, which has no answer for
        None."""
        loan = lenny.loan_from_node("lenny", NODE["issuer"], "patron", {"edition_id": 1, "borrowed_at": None})
        assert loan is not None
        assert loan["loaned_at"] == 0.0

    def test_an_unparsable_borrowed_at_is_zero_not_a_crash(self):
        loan = lenny.loan_from_node("lenny", NODE["issuer"], "patron", {"edition_id": 1, "borrowed_at": "last tuesday"})
        assert loan is not None
        assert loan["loaned_at"] == 0.0

    def test_a_provider_loan_is_marked_as_one(self):
        """`templates/account/loans.html` branches on this. Without it the loan
        reaches the Internet Archive branches, which read `ocaid` and
        `loan_link`."""
        loan = lenny.loan_from_node("lenny", NODE["issuer"], "patron", {"edition_id": 1})
        assert loan is not None
        assert loan["provider"] == "lenny"
        assert loan["resource_type"] != "bookreader"


class TestProviderLoansMerge:
    @staticmethod
    def _fetch(responses):
        """Stand in for the HTTP leg, keyed by issuer."""

        async def fetch(issuer, token, timeout_seconds):
            outcome = responses[issuer]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return fetch

    def test_loans_from_every_node_are_merged(self, two_nodes, monkeypatch):
        monkeypatch.setattr(
            lenny,
            "fetch_node_loans",
            self._fetch({NODE["issuer"]: [{"edition_id": 1}], NODE_B["issuer"]: [{"edition_id": 2}]}),
        )
        result = lenny.provider_loans("patron")
        assert [loan["book"] for loan in result.loans] == ["/books/OL1M", "/books/OL2M"]
        assert result.unreachable == []
        assert result.unauthorized == []

    def test_a_dead_node_costs_its_own_loans_and_nothing_else(self, two_nodes, monkeypatch):
        """The requirement this feature turns on: one node down must not take
        the patron's loans page with it."""
        monkeypatch.setattr(
            lenny,
            "fetch_node_loans",
            self._fetch({NODE["issuer"]: httpx.ConnectError("refused"), NODE_B["issuer"]: [{"edition_id": 2}]}),
        )
        result = lenny.provider_loans("patron")
        assert [loan["book"] for loan in result.loans] == ["/books/OL2M"]
        assert result.unreachable == ["lenny"]

    def test_every_node_down_is_still_not_an_exception(self, two_nodes, monkeypatch):
        monkeypatch.setattr(
            lenny,
            "fetch_node_loans",
            self._fetch({NODE["issuer"]: httpx.ReadTimeout("slow"), NODE_B["issuer"]: httpx.ConnectError("refused")}),
        )
        result = lenny.provider_loans("patron")
        assert result.loans == []
        assert sorted(result.unreachable) == ["lenny", "lenny_b"]

    def test_a_node_returning_junk_entries_drops_only_those(self, two_nodes, monkeypatch):
        """A list of strings where objects were promised is a node bug, not a
        reason for a 500 on the patron's loans page."""
        monkeypatch.setattr(
            lenny,
            "fetch_node_loans",
            self._fetch({NODE["issuer"]: ["not-an-object", {"edition_id": 3}], NODE_B["issuer"]: []}),
        )
        result = lenny.provider_loans("patron")
        assert [loan["book"] for loan in result.loans] == ["/books/OL3M"]
        assert result.unreachable == []

    def test_a_cleared_grant_is_unauthorized_not_unreachable(self, two_nodes, monkeypatch):
        """Different remedies -- wait, versus reconnect the library. Collapsing
        them tells the patron to do the wrong thing."""
        monkeypatch.setattr(lenny, "access_token_for", lambda username, provider_name: None if provider_name == "lenny" else "at-b")
        monkeypatch.setattr(lenny, "fetch_node_loans", self._fetch({NODE_B["issuer"]: [{"edition_id": 2}]}))
        result = lenny.provider_loans("patron")
        assert result.unauthorized == ["lenny"]
        assert result.unreachable == []
        assert [loan["book"] for loan in result.loans] == ["/books/OL2M"]

    def test_a_grant_at_an_unconfigured_node_is_skipped_silently(self, monkeypatch):
        """Nothing the patron can act on, so no note about it."""
        monkeypatch.setattr(lenny, "nodes", lambda: {"lenny": NODE})
        monkeypatch.setattr(lenny.ProviderToken, "get_providers", staticmethod(lambda username: ["lenny_retired"]))
        assert lenny.provider_loans("patron") == lenny.ProviderLoans([], [], [])

    def test_an_unreadable_token_store_renders_an_empty_merge(self, monkeypatch):
        def boom(username):
            raise RuntimeError("no database")

        monkeypatch.setattr(lenny, "nodes", lambda: {"lenny": NODE})
        monkeypatch.setattr(lenny.ProviderToken, "get_providers", staticmethod(boom))
        assert lenny.provider_loans("patron") == lenny.ProviderLoans([], [], [])

    def test_a_token_lookup_that_raises_is_unreachable_not_a_500(self, two_nodes, monkeypatch):
        def boom(username, provider_name):
            raise RuntimeError("store exploded")

        monkeypatch.setattr(lenny, "access_token_for", boom)
        result = lenny.provider_loans("patron")
        assert sorted(result.unreachable) == ["lenny", "lenny_b"]
        assert result.loans == []

    def test_each_node_is_presented_its_own_token(self, two_nodes, monkeypatch):
        seen = {}

        async def fetch(issuer, token, timeout_seconds):
            seen[issuer] = token
            return []

        monkeypatch.setattr(lenny, "fetch_node_loans", fetch)
        lenny.provider_loans("patron")
        assert seen == {NODE["issuer"]: "at-lenny", NODE_B["issuer"]: "at-lenny_b"}


class TestTheNodesAreQueriedConcurrently:
    """A patron with four providers must not wait for four timeouts.

    This is the one property a sequential loop would satisfy every other test
    in this file while failing, so it is measured in wall time rather than
    inferred from the shape of the code.
    """

    def test_four_slow_nodes_cost_one_delay_not_four(self, monkeypatch):
        delay = 0.4
        node_names = [f"lenny_{n}" for n in range(4)]
        monkeypatch.setattr(
            lenny,
            "nodes",
            lambda: {name: {**NODE, "issuer": f"https://{name}.example.org"} for name in node_names},
        )
        monkeypatch.setattr(lenny.ProviderToken, "get_providers", staticmethod(lambda username: node_names))
        monkeypatch.setattr(lenny, "access_token_for", lambda username, provider_name: "at")

        async def slow(issuer, token, timeout_seconds):
            await asyncio.sleep(delay)
            return [{"edition_id": 1}]

        monkeypatch.setattr(lenny, "fetch_node_loans", slow)

        started = time.monotonic()
        result = lenny.provider_loans("patron")
        elapsed = time.monotonic() - started

        assert len(result.loans) == 4
        assert elapsed < delay * 2, f"four nodes took {elapsed:.2f}s; sequential would be ~{delay * 4:.2f}s"


class TestTheTokenPhaseIsBounded:
    def test_a_spent_deadline_stops_resolving_further_grants(self, two_nodes, monkeypatch):
        """The token phase is sequential and synchronous -- see
        LOANS_DEADLINE_SECONDS -- so it needs a ceiling of its own rather than
        letting N expired grants at N hanging nodes add up."""
        monkeypatch.setattr(lenny, "LOANS_DEADLINE_SECONDS", 0)
        result = lenny.provider_loans("patron")
        assert sorted(result.unreachable) == ["lenny", "lenny_b"]
        assert result.loans == []
    def test_the_library_named_to_the_patron_comes_from_current_config(self, flow, monkeypatch):
        """Not from `state`, which is a ten-minute-old snapshot of the
        credentials the flow needed. A display name is the one field in there
        an operator may have corrected since."""
        monkeypatch.setattr(lenny, "nodes", lambda: {"lenny": {**NODE, "name": "Archive Labs Lenny"}})
        self._call(monkeypatch)
        assert [m.message for m in web.ctx.flash] == ["Borrowed from Archive Labs Lenny. Your loan is due 2026-09-24."]

    def test_an_unconfigured_node_still_confirms_the_loan(self, flow, monkeypatch):
        """A node dropped from config between the click and the callback: the
        loan is real, so the patron must still be told about it."""
        monkeypatch.setattr(lenny, "nodes", dict)
        self._call(monkeypatch)
        assert [m.message for m in web.ctx.flash] == ["Borrowed from Lenny. Your loan is due 2026-09-24."]


class TestNodeDisplayName:
    def test_prefers_the_name_the_operator_configured(self):
        assert lenny.node_display_name("lenny", {**NODE, "name": "Archive Labs Lenny"}) == "Archive Labs Lenny"

    def test_falls_back_to_the_provider_name(self):
        """An operator who set no name should still get a whole sentence."""
        assert lenny.node_display_name("lenny_example_org", NODE) == "Lenny Example Org"


class TestMediatedBorrow:
    """Whether a borrow runs through Open Library or is handed to the node.

    `handle_borrow_async` asks this. Getting it wrong in either direction is
    invisible from inside the handler: a false positive sends the patron into a
    handshake Open Library has no credentials for, and a false negative quietly
    reverts #13688 to #13686's hand-off.
    """

    @pytest.fixture
    def lends(self, monkeypatch):
        def configure(nodes, rows=("lenny",)):
            monkeypatch.setattr(lenny, "nodes", lambda: nodes)
            monkeypatch.setattr(
                lenny.Acquisition,
                "get_by_edition",
                staticmethod(lambda edition_id, provider_name=None: [lenny.Acquisition(provider_name=r) for r in rows]),
            )

        return configure

    def test_a_configured_node_borrows_through_open_library(self, lends):
        lends({"lenny": {**NODE, "name": "Archive Labs Lenny"}})
        assert lenny.mediated_borrow("/books/OL51008637M") == ("/borrow/lenny/OL51008637M", "Archive Labs Lenny")

    def test_the_url_is_an_open_library_path(self, lends):
        """Relative on purpose: the patron's address bar must not change host,
        which is the whole requirement behind #13688."""
        lends({"lenny": NODE})
        url, _name = lenny.mediated_borrow("/books/OL51008637M")
        assert url.startswith("/borrow/")
        assert "://" not in url

    def test_an_unconfigured_node_is_left_to_its_own_sign_in(self, lends):
        """No credentials means no handshake to run. The caller falls back to
        the URL the feed gave it, which still completes a loan."""
        lends({}, rows=("lenny",))
        assert lenny.mediated_borrow("/books/OL51008637M") is None


class TestPopupEndings:
    """The two pages the popup can end on.

    Both are `RawText`, which looks like a styling choice and is not: the site
    layout calls `get_flash_messages()`, which *drains* `web.ctx.flash`, and
    `flash_processor` then writes no cookie because the drained value matches
    the empty one that arrived. The message would be shown inside a window
    about to close and never reach the page that opened it.
    """

    @pytest.fixture(autouse=True)
    def context(self, request_context_fixture):
        request_context_fixture(lang="en")
        web.ctx.flash = []

    LOAN: ClassVar[dict] = {"edition_id": 51008637, "due_at": "2026-10-04"}
    READ = "https://lennyforlibraries.org/v1/api/items/51008637/read"

    def _flash(self):
        return [(m.type, m.message) for m in web.ctx.flash]

    def _borrowed(self):
        return lenny.render_borrowed("/books/OL51008637M", self.LOAN, self.READ, "Archive Labs Lenny")

    def test_success_is_not_rendered_through_the_site_layout(self):
        assert isinstance(self._borrowed(), lenny.delegate.RawText)

    def test_failure_is_not_rendered_through_the_site_layout(self):
        assert isinstance(lenny.render_error("Nope.", "/books/OL51008637M"), lenny.delegate.RawText)

    def test_the_confirmation_the_patron_reads_is_a_flash_on_the_page_behind(self):
        """The popup closes before anything on it can be read, so the success
        page is not where the patron is told the loan exists."""
        self._borrowed()
        assert self._flash() == [("info", "Borrowed from Archive Labs Lenny. Your loan is due 2026-10-04.")]

    def test_a_loan_with_no_due_date_still_confirms(self):
        lenny.render_borrowed("/books/OL51008637M", {"edition_id": 1}, self.READ, "Archive Labs Lenny")
        assert self._flash() == [("info", "Borrowed from Archive Labs Lenny.")]

    def test_a_failure_is_shown_here_and_not_also_flashed(self):
        """The failure page stays on screen to be read, so a flash onto the
        page behind it would show the patron the same sentence twice."""
        page = lenny.render_error("Every copy is currently on loan.", "/books/OL51008637M")
        assert "Every copy is currently on loan." in page.rawtext
        assert self._flash() == []

    def test_the_success_page_keeps_a_route_to_the_book(self):
        """The only route, on the paths with no opener to refresh: Open
        Library's own button still says "Borrow" after a loan."""
        assert self.READ in self._borrowed().rawtext

    def test_the_success_page_carries_the_type_the_opener_listens_for(self):
        """A mismatch here is the loan created and the page never refreshed."""
        assert f'data-message-type="{lenny.POPUP_MESSAGE_TYPE}"' in self._borrowed().rawtext

    def test_the_result_is_posted_to_this_origin_only(self):
        """A `*` target origin would hand the result to whatever page happens
        to be the opener."""
        rawtext = self._borrowed().rawtext
        assert "postMessage(" in rawtext
        assert "window.location.origin" in rawtext
        assert "'*'" not in rawtext

    def test_a_failure_shows_the_reason_rather_than_closing(self):
        page = lenny.render_error("Every copy is currently on loan.", "/books/OL51008637M")
        assert "Every copy is currently on loan." in page.rawtext
        assert 'data-ok="0"' in page.rawtext

    def test_an_expired_request_with_no_book_to_return_to_still_renders(self):
        """`render_error`'s one caller without a pending state: a callback whose
        state has expired knows no edition."""
        assert 'data-return-url="/"' in lenny.render_error("That borrow request expired.").rawtext

    def test_the_listener_in_the_bundle_agrees_on_the_message_type(self):
        """The one contract in this feature that spans two languages, so the
        only thing that can hold it is a test that reads both sides.

        Renaming the constant here and not in the module the book page loads
        is silent: the loan is created, the message is posted, nothing is
        listening for that type, and the page never refreshes. Neither a Python
        test of the callback nor a JavaScript test of the listener sees it,
        because each is internally consistent.
        """
        module = pathlib.Path(lenny.__file__).resolve().parents[2] / "plugins/openlibrary/js/provider_borrow_popup.js"
        assert f"const MESSAGE_TYPE = '{lenny.POPUP_MESSAGE_TYPE}';" in module.read_text()
