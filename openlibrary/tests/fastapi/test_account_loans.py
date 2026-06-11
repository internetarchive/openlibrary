"""Tests for the FastAPI account loan endpoints."""

import json
from contextlib import nullcontext
from unittest.mock import Mock, patch

import pytest
import web
from starlette.requests import Request

from infogami.utils.context import context as legacy_context
from openlibrary.plugins.upstream import account as legacy_account
from openlibrary.utils import request_context


class FakeLegacyUser(dict):
    def __init__(self, username: str = "testuser"):
        key = f"/people/{username}"
        super().__init__(key=key)
        self.key = key
        self.update_loan_status = Mock()


class FakeEdition:
    def dict(self) -> dict:
        return {"key": "/books/OL1M", "title": "Serialized Edition"}


def _mock_legacy_context():
    return patch("openlibrary.fastapi.account.legacy_web_ctx_from_fastapi", return_value=nullcontext())


class TestLegacyContextBridge:
    def test_legacy_context_bridge_populates_infogami_template_context(self):
        legacy_user = FakeLegacyUser()
        legacy_site = Mock(_conn=Mock())
        legacy_site.get_user.return_value = legacy_user
        original_legacy_context = legacy_context.copy()
        legacy_context.clear()
        legacy_context.previous_value = "kept"
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "scheme": "http",
                "path": "/account/loans.json",
                "query_string": b"rescue=true",
                "headers": [(b"host", b"testserver")],
                "client": ("127.0.0.1", 1234),
                "server": ("testserver", 80),
            }
        )
        request.state.lang = "en"
        site_token = request_context.site.set(legacy_site)

        try:
            with request_context.legacy_web_ctx_from_fastapi(request):
                assert web.ctx.path == "/account/loans.json"
                assert web.ctx.encoding == "json"
                assert web.ctx.render_once == {}
                assert web.ctx.site == legacy_site
                assert legacy_context.path == "/account/loans.json"
                assert legacy_context.user == legacy_user
                assert legacy_context.rescue_mode is True

            assert legacy_context.previous_value == "kept"
            assert "path" not in legacy_context
        finally:
            request_context.site.reset(site_token)
            legacy_context.clear()
            legacy_context.update(original_legacy_context)


class TestAccountLoansJson:
    @pytest.mark.parametrize("path", ["/account/loans.json", "/account/loan-history.json"])
    def test_json_endpoints_return_401_when_unauthenticated(self, fastapi_client, path):
        response = fastapi_client.get(path)

        assert response.status_code == 401

    def test_loans_json_updates_loan_status_and_returns_loans(self, fastapi_client, mock_authenticated_user):
        legacy_user = FakeLegacyUser()
        loans = [{"book": "/books/OL1M", "ocaid": "test_ocaid"}]

        with (
            _mock_legacy_context(),
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
            _mock_legacy_context(),
            patch("openlibrary.fastapi.account.accounts.get_current_user", return_value=legacy_user),
            patch("openlibrary.plugins.upstream.account.get_account_loan_history_data", return_value=loan_history_data) as get_data,
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
        get_data.assert_called_once_with(legacy_user, page)

    def test_loan_history_json_rejects_invalid_page(self, fastapi_client, mock_authenticated_user):
        response = fastapi_client.get("/account/loan-history.json?page=0")

        assert response.status_code == 422

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
            _mock_legacy_context(),
            patch("openlibrary.fastapi.account.accounts.get_current_user", return_value=legacy_user),
            patch("openlibrary.fastapi.account.legacy_account.get_account_loans_json", return_value=expected),
        ):
            fastapi_response = fastapi_client.get("/account/loans.json")

        assert fastapi_response.status_code == 200
        assert fastapi_response.json() == json.loads(legacy_response.rawtext)
