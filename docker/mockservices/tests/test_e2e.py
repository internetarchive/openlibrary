"""
End-to-end tests against the live mockservices container.

Requires the mockservices container to be up and reachable. Starting `web`
also starts `mockservices` (see compose.override.yaml's `depends_on`):

    OL_MOUNT_DIR=$(pwd) docker compose up -d web

Run from a container on the `webnet` docker network (e.g. `home`), which
can reach mockservices directly by service name:

    docker compose run --rm home pytest docker/mockservices/tests/test_e2e.py -v

Each test hits mockservices with the exact wire format the real OL client
code sends (see openlibrary/accounts/model.py, openlibrary/core/lending.py),
not just what's convenient to construct.
"""

import os

import pytest
import requests

MOCKSERVICES_URL = os.environ.get("MOCKSERVICES_URL", "http://mockservices:8090")


def _get(path, **kwargs):
    return requests.get(f"{MOCKSERVICES_URL}{path}", timeout=5, **kwargs)


def _post(path, **kwargs):
    return requests.post(f"{MOCKSERVICES_URL}{path}", timeout=5, **kwargs)


@pytest.fixture(scope="module", autouse=True)
def _require_mockservices():
    try:
        resp = _get("/health")
    except requests.ConnectionError:
        pytest.skip(f"mockservices not reachable at {MOCKSERVICES_URL} — is docker compose up?")
    if resp.status_code != 200:
        pytest.skip("mockservices did not report healthy")


def test_health():
    resp = _get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "ol-mockservices"}


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
        # Every dev login resolves to the seeded admin account.
        assert body["values"]["screenname"] == "openlibrary"

    def test_authenticate_fails_without_password(self):
        resp = _post(
            "/services/xauthn/",
            params={"op": "authenticate"},
            json={"email": "test@example.com"},
        )
        body = resp.json()
        assert body["success"] is False
        assert body["values"]["reason"]

    def test_authenticate_fails_with_sentinel_bad_password(self):
        resp = _post(
            "/services/xauthn/",
            params={"op": "authenticate"},
            json={"email": "test@example.com", "password": "bad_password"},
        )
        body = resp.json()
        assert body["success"] is False
        assert body["values"]["reason"] == "bad_password"

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


class TestLoansLifecycle:
    def test_loan_query_empty_by_default(self):
        resp = _post("/services/loans/loan/", json={"method": "loan.query", "userid": "@test_user_empty"})
        assert resp.status_code == 200
        assert resp.json() == {"result": []}

    def test_borrow_and_query_and_return_lifecycle(self):
        user = "@test_patron_1"
        book_id = "testbook123"

        # 1. Borrow book
        borrow_resp = _post(
            "/services/loans/loan/",
            data={"action": "borrow_book", "identifier": book_id, "userid": user},
        )
        assert borrow_resp.status_code == 200
        borrow_data = borrow_resp.json()
        assert borrow_data.get("status") == "ok"
        assert borrow_data["result"]["loan"]["identifier"] == book_id
        assert borrow_data["result"]["loan"]["userid"] == user

        # 2. Query active loans
        query_resp = _post(
            "/services/loans/loan/",
            json={"method": "loan.query", "userid": user},
        )
        assert query_resp.status_code == 200
        active_loans = query_resp.json().get("result", [])
        assert any(loan["identifier"] == book_id for loan in active_loans)

        # 3. Return book
        return_resp = _post(
            "/services/loans/loan/",
            data={"action": "return_loan", "identifier": book_id, "userid": user},
        )
        assert return_resp.status_code == 200
        assert return_resp.json().get("status") == "ok"

        # 4. Query active loans again - should be empty
        query_resp2 = _post(
            "/services/loans/loan/",
            json={"method": "loan.query", "userid": user},
        )
        assert query_resp2.status_code == 200
        assert not any(loan["identifier"] == book_id for loan in query_resp2.json().get("result", []))

        # 5. Query user borrow history
        history_resp = _post(
            "/services/loans/loan/",
            data={"action": "user_borrow_history", "userid": user},
        )
        assert history_resp.status_code == 200
        history_items = history_resp.json().get("history", {}).get("items", [])
        assert any(item["identifier"] == book_id for item in history_items)


class TestAvailability:
    def test_availability_get(self):
        resp = _get("/services/availability/", params={"identifier": "book1,book2"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "book1" in body["responses"]
        assert "book2" in body["responses"]
        assert "status" in body["responses"]["book1"]

    def test_availability_post_json(self):
        resp = _post("/services/availability/", json={"identifier": ["bookA", "bookB"]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "bookA" in body["responses"]
        assert "bookB" in body["responses"]

    def test_availability_deterministic_results(self):
        resp1 = _get("/services/availability/", params={"identifier": "fixed_book_id"})
        resp2 = _get("/services/availability/", params={"identifier": "fixed_book_id"})
        assert resp1.json()["responses"]["fixed_book_id"] == resp2.json()["responses"]["fixed_book_id"]


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


# ---------------------------------------------------------------------------
# Matomo mock — the parts that need a live container.
#
# Everything else about this endpoint is covered by test_matomo_inprocess.py,
# which serves the same app on a loopback port and therefore also runs in CI.
# Only keep tests here that genuinely require the deployed container.
# ---------------------------------------------------------------------------


class TestMatomoMock:
    def test_rejects_unimplemented_methods(self):
        resp = _post("/matomo/index.php", data={"method": "SitesManager.getAllSites", "token_auth": "t"})
        assert resp.json()["result"] == "error"
