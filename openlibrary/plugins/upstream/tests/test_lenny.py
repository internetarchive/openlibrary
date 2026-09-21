"""Tests for the Lenny borrow flow (#12844).

Weighted towards the failure paths. The happy path is one HTTP round trip and
hard to get wrong; the security of this flow lives entirely in what it
*refuses* -- a replayed callback, a code from the wrong node, a node that does
not offer S256 -- and a check nothing proves is a check that does not work.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import urllib.parse
from typing import ClassVar

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
    def test_returns_none_for_an_unparseable_key(self, monkeypatch):
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

    def test_an_unparseable_expires_in_raises(self):
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
    def flow(self, memcache, monkeypatch):
        """A pending authorization, with every side effect recorded."""
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
        assert "could not be verified" in body
        assert flow["order"] == []

    def test_a_missing_iss_aborts_before_the_code_is_spent(self, flow, monkeypatch):
        body = self._call(monkeypatch, iss=None)
        assert "could not be verified" in body
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
        assert "could not complete the loan" in body
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
        assert "expired" in body
        assert flow["order"] == []
