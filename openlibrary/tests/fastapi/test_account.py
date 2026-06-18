"""Tests for FastAPI account endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from openlibrary.core.auth import ExpiredTokenError, MissingKeyError
from openlibrary.utils.request_context import RequestContextVars, req_context, site

_DEFAULT_HEADER = "LOW ak:sk"
_SENTINEL = object()


def _anonymize_post(
    client,
    *,
    data=None,
    headers=None,
    hmac_return_value=True,
    hmac_side_effect=None,
    s3auth_result=None,
    get_by_link_result=_SENTINEL,
    anonymize_return_value=None,
    anonymize_side_effect=None,
):
    if data is None:
        data = {"digest": "d", "msg": "m"}
    if headers is None:
        headers = {"Authorization": _DEFAULT_HEADER}

    hmac_kw = {}
    if hmac_side_effect is not None:
        hmac_kw["side_effect"] = hmac_side_effect
    else:
        hmac_kw["return_value"] = hmac_return_value

    if s3auth_result is None:
        s3auth_result = {"itemname": "test-item"}

    if get_by_link_result is _SENTINEL:
        mock_account = MagicMock()
        mock_account.username = "testuser"
        mock_account.anonymize.return_value = anonymize_return_value or {
            "new_username": "anonymous-abc123",
            "booknotes_count": 0,
            "ratings_count": 0,
            "observations_count": 0,
            "bookshelves_count": 0,
            "merge_request_count": 0,
            "bestbooks_count": 0,
        }
        get_by_link_return = mock_account
    else:
        mock_account = get_by_link_result
        get_by_link_return = get_by_link_result

    if anonymize_side_effect is not None:
        mock_account.anonymize.side_effect = anonymize_side_effect

    _site_token = site.set(MagicMock())
    _req_token = req_context.set(
        RequestContextVars(
            x_forwarded_for=None,
            user_agent=None,
            lang="en",
            solr_editions=True,
            print_disabled=False,
        )
    )
    try:
        with (
            patch("openlibrary.fastapi.account.HMACToken.verify", **hmac_kw),
            patch("openlibrary.fastapi.account.InternetArchiveAccount.s3auth", return_value=s3auth_result),
            patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_link", return_value=get_by_link_return),
            patch("openlibrary.fastapi.account.RunAs"),
            patch("openlibrary.fastapi.account.logger"),
        ):
            response = client.post(
                "/account/anonymize.json",
                data=data,
                headers=headers,
            )
    finally:
        site.reset(_site_token)
        req_context.reset(_req_token)

    return response, mock_account


def test_login_deletes_pending_action_cookie_on_valid_redirect(fastapi_client):
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
    ):
        mock_audit.return_value = {"ol_username": "testuser"}
        mock_gen_code.return_value = "token"

        response = fastapi_client.post(
            "/account/login",
            data={"username": "testuser", "password": "password", "redirect": "/books"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["Location"] == "/books"

        set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
        assert any("pending_action=" in header for header in set_cookies)

        response = fastapi_client.post(
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


class TestAnonymizeAccount:
    def test_success(self, fastapi_client):
        resp, mock_account = _anonymize_post(fastapi_client)

        assert resp.status_code == 200
        data = resp.json()
        assert data["new_username"] == "anonymous-abc123"
        mock_account.anonymize.assert_called_once_with(test=False)

    def test_success_with_test_mode(self, fastapi_client):
        resp, mock_account = _anonymize_post(
            fastapi_client,
            data={"test": "true", "digest": "d", "msg": "m"},
        )

        assert resp.status_code == 200
        mock_account.anonymize.assert_called_once_with(test=True)

    def test_hmac_failure(self, fastapi_client):
        resp, _ = _anonymize_post(fastapi_client, hmac_return_value=False)

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Unauthorized"

    def test_expired_token(self, fastapi_client):
        resp, _ = _anonymize_post(fastapi_client, hmac_side_effect=ExpiredTokenError())

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Unauthorized"

    def test_missing_key(self, fastapi_client):
        resp, _ = _anonymize_post(fastapi_client, hmac_side_effect=MissingKeyError())

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Service Unavailable"

    def test_bad_hmac_format(self, fastapi_client):
        resp, _ = _anonymize_post(fastapi_client, hmac_side_effect=ValueError())

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Bad Request"

    def test_malformed_auth_header(self, fastapi_client):
        resp, _ = _anonymize_post(fastapi_client, headers={"Authorization": "BAD bad_format"})

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Malformed Authorization Header"

    def test_missing_auth_header(self, fastapi_client):
        resp, _ = _anonymize_post(fastapi_client, headers={})

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Malformed Authorization Header"

    def test_s3_auth_failure(self, fastapi_client):
        resp, _ = _anonymize_post(fastapi_client, s3auth_result={"error": "not found"})

        assert resp.status_code == 404

    def test_account_not_found(self, fastapi_client):
        resp, _ = _anonymize_post(fastapi_client, get_by_link_result=None)

        assert resp.status_code == 404

    def test_internal_error(self, fastapi_client):
        mock_account = MagicMock()
        mock_account.username = "testuser"
        mock_account.anonymize.side_effect = RuntimeError("something went wrong")

        resp, _ = _anonymize_post(fastapi_client, get_by_link_result=mock_account)

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Internal Server Error"
