"""
End-to-end tests against the live ghostwriter container.

Requires the ghostwriter container to be up and reachable. Starting `web`
also starts `ghostwriter` (see compose.override.yaml's `depends_on`):

    OL_MOUNT_DIR=$(pwd) docker compose up -d web

Run from a container on the `webnet` docker network (e.g. `home`), which
can reach ghostwriter directly by service name:

    docker compose run --rm home pytest docker/ghostwriter/tests/test_e2e.py -v

Each test hits ghostwriter with the exact wire format the real OL client
code sends (see openlibrary/accounts/model.py, openlibrary/core/lending.py),
not just what's convenient to construct.
"""

import os

import pytest
import requests

GHOSTWRITER_URL = os.environ.get("GHOSTWRITER_URL", "http://ghostwriter:8090")


def _get(path, **kwargs):
    return requests.get(f"{GHOSTWRITER_URL}{path}", timeout=5, **kwargs)


def _post(path, **kwargs):
    return requests.post(f"{GHOSTWRITER_URL}{path}", timeout=5, **kwargs)


@pytest.fixture(scope="module", autouse=True)
def _require_ghostwriter():
    try:
        resp = _get("/health")
    except requests.ConnectionError:
        pytest.skip(f"ghostwriter not reachable at {GHOSTWRITER_URL} — is docker compose up?")
    if resp.status_code != 200:
        pytest.skip("ghostwriter did not report healthy")


def test_health():
    resp = _get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "ol-ghostwriter"}


class TestXauthn:
    """InternetArchiveAccount.xauth() sends `op` as a query param and the
    payload as a JSON body, and reads `success` from the response — every
    test here matches that wire format exactly."""

    def test_authenticate_succeeds_with_password(self):
        resp = _post(
            "/services/xauthn/",
            params={"op": "authenticate"},
            json={"email": "test@example.com", "password": "test"},
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["values"]["token"]
        assert body["values"]["email"] == "test@example.com"

    def test_authenticate_fails_without_password(self):
        resp = _post(
            "/services/xauthn/",
            params={"op": "authenticate"},
            json={"email": "test@example.com"},
        )
        body = resp.json()
        assert body["success"] is False
        assert body["values"]["reason"]

    def test_info(self):
        resp = _post("/services/xauthn/", params={"op": "info"}, json={})
        body = resp.json()
        assert body["success"] is True
        assert "email" in body["values"]

    def test_issue_otp(self):
        resp = _post("/services/xauthn/", params={"op": "issue_otp"}, json={"email": "test@example.com"})
        assert resp.json()["success"] is True

    def test_redeem_otp_correct_code(self):
        # xauth("redeem_otp", ..., password=otp) sends the OTP in the "password" field
        resp = _post(
            "/services/xauthn/",
            params={"op": "redeem_otp"},
            json={"email": "test@example.com", "password": "123456"},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["values"]["token"]

    def test_redeem_otp_wrong_code(self):
        resp = _post(
            "/services/xauthn/",
            params={"op": "redeem_otp"},
            json={"email": "test@example.com", "password": "000000"},
        )
        assert resp.json()["success"] is False

    def test_issue_key(self):
        resp = _post("/services/xauthn/", params={"op": "issue_key"}, json={"key_type": "s3"})
        body = resp.json()
        assert body["success"] is True
        assert body["s3"]["access"]
        assert body["s3"]["secret"]

    def test_create(self):
        resp = _post(
            "/services/xauthn/",
            params={"op": "create"},
            json={"email": "new@example.com", "screenname": "newbie", "password": "test"},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["values"]["screenname"] == "newbie"

    def test_activate(self):
        resp = _post("/services/xauthn/", params={"op": "activate"}, json={"token": "abc"})
        body = resp.json()
        assert body["success"] is True
        assert body["values"]["token"]

    def test_unknown_op_returns_400(self):
        resp = _post("/services/xauthn/", params={"op": "bogus"}, json={})
        assert resp.status_code == 400
        assert resp.json()["success"] is False


class TestS3Auth:
    def test_authorized(self):
        resp = _get("/services/s3auth/", headers={"Authorization": "LOW foo:foo"})
        assert resp.json()["authorized"] is True

    def test_unauthorized_missing_header(self):
        resp = _get("/services/s3auth/")
        assert resp.status_code == 401
        assert resp.json()["authorized"] is False


def test_loan_post_returns_empty_success():
    resp = _post("/services/loans/loan/")
    assert resp.status_code == 200
    assert resp.json() == {}


def test_availability_post():
    resp = _post("/services/availability/")
    assert resp.status_code == 200
    assert "responses" in resp.json()


def test_borrow_status():
    resp = _get("/services/borrow/someocaid")
    body = resp.json()
    assert resp.status_code == 200
    assert body["identifier"] == "someocaid"


class TestLoanChangesFeed:
    """GET /services/loans/loan/?action=changes mocks IA's loan changes feed
    needed by scripts/solr_updater/loan_availability_updater.py (see
    get_loan_changes() in openlibrary/core/lending.py)."""

    def test_catchup_seeds_events_in_increasing_uid_order(self):
        resp = _get("/services/loans/loan/", params={"action": "changes", "after_uid": 0, "limit": 2000})
        body = resp.json()
        assert body["status"] == "OK"
        assert body["rows"], "expected at least some seeded rows"
        uids = [row["uid"] for row in body["rows"]]
        assert uids == sorted(uids), "rows must be in monotonically increasing uid order"

    def test_pagination_respects_after_uid(self):
        first = _get("/services/loans/loan/", params={"action": "changes", "after_uid": 0, "limit": 1}).json()
        first_uid = first["rows"][0]["uid"]
        second = _get(
            "/services/loans/loan/",
            params={"action": "changes", "after_uid": first_uid, "limit": 1},
        ).json()
        assert second["rows"][0]["uid"] > first_uid

    def test_row_shape_matches_get_loan_changes_contract(self):
        resp = _get("/services/loans/loan/", params={"action": "changes", "after_uid": 0, "limit": 1})
        row = resp.json()["rows"][0]
        for key in ("time", "identifier", "username", "loan_id", "event_type", "extra", "uid"):
            assert key in row

    def test_unsupported_action_returns_400(self):
        resp = _get("/services/loans/loan/", params={"action": "bogus"})
        assert resp.status_code == 400

    def test_missing_action_returns_422(self):
        resp = _get("/services/loans/loan/")
        assert resp.status_code == 422
