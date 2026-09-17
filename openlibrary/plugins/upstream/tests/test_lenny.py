"""Tests for the Lenny borrow flow (#12844).

Weighted towards the failure paths. The happy path is one HTTP round trip and
hard to get wrong; the security of this flow lives entirely in what it
*refuses* -- a replayed callback, a code from the wrong node, a node that does
not offer S256 -- and a check nothing proves is a check that does not work.
"""

from __future__ import annotations

import base64
import hashlib
from typing import ClassVar

import pytest

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
        assert lenny.exchange_code(pending, "code-xyz") == ("at-123", "rt-456")
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
        assert lenny.exchange_code(pending, "code") == ("at-only", "")

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
