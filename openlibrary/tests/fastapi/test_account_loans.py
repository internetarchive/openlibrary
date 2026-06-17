"""Tests for the FastAPI account loan endpoints."""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest
import web

from openlibrary.plugins.upstream import account as legacy_account


class FakeLegacyUser(dict):
    def __init__(self, username: str = "testuser"):
        key = f"/people/{username}"
        super().__init__(key=key)
        self.key = key
        self.update_loan_status = Mock()


class FakeEdition:
    def dict(self) -> dict:
        return {"key": "/books/OL1M", "title": "Serialized Edition"}


class TestAccountLoansJson:
    @pytest.mark.parametrize("path", ["/account/loans.json", "/account/loan-history.json"])
    def test_json_endpoints_return_401_when_unauthenticated(self, fastapi_client, path):
        response = fastapi_client.get(path)

        assert response.status_code == 401

    def test_loans_json_updates_loan_status_and_returns_loans(self, fastapi_client, mock_authenticated_user):
        legacy_user = FakeLegacyUser()
        loans = [{"book": "/books/OL1M", "ocaid": "test_ocaid"}]

        with (
            patch("openlibrary.fastapi.account.accounts.get_current_user", return_value=legacy_user),
            patch("openlibrary.plugins.upstream.account.borrow.get_loans", return_value=loans) as get_loans,
        ):
            response = fastapi_client.get("/account/loans.json")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"loans": loans}
        legacy_user.update_loan_status.assert_called_once_with()
        get_loans.assert_called_once_with(legacy_user)

    @pytest.mark.parametrize(
        ("path", "page"),
        [
            ("/account/loan-history.json", 1),
            ("/account/loan-history.json?page=2", 2),
        ],
    )
    def test_loan_history_json_serializes_docs_and_forwards_page(self, fastapi_client, mock_authenticated_user, path, page):
        legacy_user = FakeLegacyUser()
        loan_history_data = {
            "docs": [{"key": "/books/OL2M", "title": "Raw dict"}, FakeEdition()],
            "show_next": True,
            "limit": 25,
            "page": page,
        }

        with (
            patch("openlibrary.fastapi.account.accounts.get_current_user", return_value=legacy_user),
            patch("openlibrary.plugins.upstream.account.MyBooksTemplate", return_value=MagicMock()),
            patch("openlibrary.plugins.upstream.account.get_loan_history_data", return_value=loan_history_data) as get_data,
        ):
            response = fastapi_client.get(path)

        assert response.status_code == 200
        assert response.json() == {
            "loans_history": {
                "docs": [
                    {"key": "/books/OL2M", "title": "Raw dict"},
                    {"key": "/books/OL1M", "title": "Serialized Edition"},
                ],
                "show_next": True,
                "limit": 25,
                "page": page,
            }
        }
        assert get_data.called
        assert get_data.call_args.kwargs["page"] == page

    def test_loan_history_json_rejects_invalid_page(self, fastapi_client, mock_authenticated_user):
        response = fastapi_client.get("/account/loan-history.json?page=0")

        assert response.status_code == 422

    @pytest.mark.parametrize(
        ("endpoint", "helper_path"),
        [
            ("/account/loans.json", "openlibrary.fastapi.account.legacy_account.get_account_loans_json"),
            ("/account/loan-history.json", "openlibrary.fastapi.account.legacy_account.get_account_loan_history_json"),
        ],
    )
    def test_local_dev_returns_503_with_helpful_message(self, fastapi_client, mock_authenticated_user, endpoint, helper_path, monkeypatch):
        monkeypatch.setenv("LOCAL_DEV", "true")
        legacy_user = FakeLegacyUser()

        with (
            patch("openlibrary.fastapi.account.accounts.get_current_user", return_value=legacy_user),
            patch(helper_path, side_effect=ConnectionError("Unable to reach archive.org")),
        ):
            response = fastapi_client.get(endpoint)

        assert response.status_code == 503
        assert "production Internet Archive" in response.json()["detail"]

    def test_legacy_and_fastapi_loans_json_match_shared_helper_response(self, fastapi_client, mock_authenticated_user, monkeypatch):
        legacy_user = FakeLegacyUser()
        expected = {"loans": [{"book": "/books/OL1M", "ocaid": "test_ocaid"}]}
        site = Mock()
        site.get_user.return_value = legacy_user
        web.ctx.headers = []
        monkeypatch.setattr(web.ctx, "site", site, raising=False)

        with (
            patch("openlibrary.plugins.upstream.account.accounts.get_current_user", return_value=legacy_user),
            patch("openlibrary.plugins.upstream.account.get_account_loans_json", return_value=expected),
            pytest.deprecated_call(match="migrated to fastapi"),
        ):
            legacy_response = legacy_account.account_loans_json().GET()

        with (
            patch("openlibrary.fastapi.account.accounts.get_current_user", return_value=legacy_user),
            patch("openlibrary.fastapi.account.legacy_account.get_account_loans_json", return_value=expected),
        ):
            fastapi_response = fastapi_client.get("/account/loans.json")

        assert fastapi_response.status_code == 200
        assert fastapi_response.json() == json.loads(legacy_response.rawtext)
