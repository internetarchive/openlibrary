"""Tests for FastAPI account endpoints."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from openlibrary.asgi_app import app


def test_login_deletes_pending_action_cookie_on_valid_redirect():
    client = TestClient(app)
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
    ):
        mock_audit.return_value = {"ol_username": "testuser"}
        mock_gen_code.return_value = "token"

        # Case 1: Valid redirect -> deletes preserve intent cookie
        response = client.post(
            "/account/login",
            data={"username": "testuser", "password": "password", "redirect": "/books"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["Location"] == "/books"

        # Check if the set-cookie header deletes "pending_action"
        set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
        assert any("pending_action=" in header for header in set_cookies)

        # Case 2: Invalid/unsafe redirect -> does not delete cookie, redirects to home /
        response = client.post(
            "/account/login",
            data={
                "username": "testuser",
                "password": "password",
                "redirect": "http://evil.com",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["Location"] == "/"

        set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
        assert not any("pending_action=" in header for header in set_cookies)
