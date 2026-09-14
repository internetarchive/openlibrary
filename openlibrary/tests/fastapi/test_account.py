"""Tests for FastAPI account endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.parse import unquote

from infogami import config
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
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=None),
    ):
        mock_audit.return_value = {"ol_username": "testuser"}
        mock_gen_code.return_value = "token"

        # Case 1: Valid redirect -> deletes preserve intent cookie
        response = fastapi_client.post(
            "/account/login",
            data={"username": "testuser", "password": "password", "redirect": "/books"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["Location"] == "/books"

        # Check if the set-cookie header deletes "pending_action"
        set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
        assert any("pending_action=" in header for header in set_cookies)

        # Case 2: Invalid/unsafe redirect -> does not delete cookie, redirects to
        # /account/books (same fallback as web.py)
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
        assert response.headers["Location"] == "/account/books"

        set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
        assert not any("pending_action=" in header for header in set_cookies)

        # Case 3: Blacklisted redirect -> /account/books
        response = fastapi_client.post(
            "/account/login",
            data={
                "username": "testuser",
                "password": "password",
                "redirect": "/account/login",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["Location"] == "/account/books"

        # Case 4: Backslash open-redirect (browsers normalize /\host) -> blocked
        response = fastapi_client.post(
            "/account/login",
            data={
                "username": "testuser",
                "password": "password",
                "redirect": "/\\evil.com",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["Location"] == "/account/books"

        # Case 5: No redirect -> /account/books (web.py default)
        response = fastapi_client.post(
            "/account/login",
            data={"username": "testuser", "password": "password"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["Location"] == "/account/books"


def test_login_with_s3_form_fields_does_not_422(fastapi_client):
    """S3-key login via form fields must work without username/password, like web.py."""
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=None),
    ):
        mock_audit.return_value = {"ol_username": "testuser"}
        mock_gen_code.return_value = "token"

        response = fastapi_client.post(
            "/account/login",
            data={"access": "ak", "secret": "sk"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["Location"] == "/account/books"
        _, kwargs = mock_audit.call_args
        assert kwargs["email"] == ""
        assert kwargs["s3_access_key"] == "ak"
        assert kwargs["s3_secret_key"] == "sk"


def test_login_with_query_string_params(fastapi_client):
    """openlibrary/api.py logs in via query string params, like web.py's web.input()."""
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=None),
    ):
        mock_audit.return_value = {"ol_username": "testuser"}
        mock_gen_code.return_value = "token"

        response = fastapi_client.post(
            "/account/login?username=queryuser&password=querypass&test=true",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["Location"] == "/account/books"
        _, kwargs = mock_audit.call_args
        assert kwargs["email"] == "queryuser"
        assert kwargs["password"] == "querypass"
        assert kwargs["test"] is True


def test_login_json_with_s3_keys(fastapi_client):
    """JSON login with S3 keys mirrors web.py's account_login_json."""
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=None),
    ):
        mock_audit.return_value = {"ol_username": "testuser"}
        mock_gen_code.return_value = "token"

        response = fastapi_client.post(
            "/account/login",
            json={"access": "ak", "secret": "sk"},
            follow_redirects=False,
        )
        assert response.status_code == 200
        _, kwargs = mock_audit.call_args
        assert kwargs["email"] is None
        assert kwargs["s3_access_key"] == "ak"
        assert kwargs["s3_secret_key"] == "sk"
        set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
        assert any(header.startswith(f"{config.login_cookie_name}=") for header in set_cookies)


def test_login_json_s3_keys_sets_sfw_cookie(fastapi_client):
    """JSON S3 login must set the sfw cookie like web.py's account_login_json
    (which looks up the OL account via the audit email)."""
    mock_user = MagicMock()
    mock_user.get_safe_mode.return_value = "yes"
    mock_user.preferences.return_value = {}
    mock_account = MagicMock()
    mock_account.get_user.return_value = mock_user
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=mock_account) as mock_get_by_email,
    ):
        mock_audit.return_value = {
            "ol_username": "testuser",
            "ia_email": "test@example.com",
        }
        mock_gen_code.return_value = "token"

        response = fastapi_client.post(
            "/account/login",
            json={"access": "ak", "secret": "sk"},
            follow_redirects=False,
        )
        assert response.status_code == 200
        mock_get_by_email.assert_called_once_with("test@example.com")
        set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
        assert any(header.startswith("sfw=yes") for header in set_cookies)


def test_login_deletes_pd_cookie_without_special_access(fastapi_client):
    """No special access -> pd cookie is deleted (Max-Age=0), like web.py's expires=1."""
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=None),
    ):
        mock_audit.return_value = {"ol_username": "testuser"}
        mock_gen_code.return_value = "token"

        response = fastapi_client.post(
            "/account/login",
            data={"username": "testuser", "password": "password", "remember": "true"},
            follow_redirects=False,
        )
        set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
        pd_cookie = next(header for header in set_cookies if header.startswith("pd="))
        assert "Max-Age=0" in pd_cookie


def test_login_sets_pd_cookie_with_special_access(fastapi_client):
    """Special access -> pd=1 cookie is set (and persists a year with remember)."""
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=None),
    ):
        mock_audit.return_value = {"ol_username": "testuser", "special_access": True}
        mock_gen_code.return_value = "token"

        response = fastapi_client.post(
            "/account/login",
            data={"username": "testuser", "password": "password", "remember": "true"},
            follow_redirects=False,
        )
        set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
        pd_cookie = next(header for header in set_cookies if header.startswith("pd=1"))
        assert "Max-Age=31536000" in pd_cookie


def test_login_json_bad_s3_keys_returns_400(fastapi_client):
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=None),
    ):
        mock_audit.return_value = {"error": "invalid_s3keys"}

        response = fastapi_client.post(
            "/account/login",
            json={"access": "bad", "secret": "bad"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_s3keys"
        assert "errorDisplayString" in data
        mock_gen_code.assert_not_called()


def test_login_json_falls_back_to_infogami_login(fastapi_client):
    """JSON username/password falls back to infogami's login, same as web.py."""
    mock_site_instance = MagicMock()
    mock_site_instance._conn.get_auth_token.return_value = "auth_token"
    mock_site = MagicMock()
    mock_site.get.return_value = mock_site_instance

    with patch("openlibrary.fastapi.account.site", mock_site):
        response = fastapi_client.post(
            "/account/login",
            json={"username": "openlibrary", "password": "secret"},
            follow_redirects=False,
        )
    assert response.status_code == 200
    mock_site_instance.login.assert_called_once_with("openlibrary", "secret")
    set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
    assert any(header.startswith(f"{config.login_cookie_name}=auth_token") for header in set_cookies)


def test_login_missing_username_redirects_to_login_not_422(fastapi_client):
    """Missing username/password goes through the audit error path (like web.py),
    not a 422 validation error."""
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=None),
    ):
        mock_audit.return_value = {"error": "missing_fields"}

        response = fastapi_client.post(
            "/account/login",
            data={"password": "secret"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["Location"].startswith("/account/login")
        _, kwargs = mock_audit.call_args
        assert kwargs["email"] == ""


def test_login_sets_s3_cookie_when_s3_keys_present(fastapi_client):
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
        patch("openlibrary.fastapi.account.encrypt_s3_keys", return_value="encrypted_token") as mock_encrypt,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=None),
    ):
        mock_audit.return_value = {
            "ol_username": "testuser",
            "s3_keys": {"access": "test_access", "secret": "test_secret"},
        }
        mock_gen_code.return_value = "token"

        response = fastapi_client.post(
            "/account/login",
            data={"username": "testuser", "password": "password"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        mock_encrypt.assert_called_once_with("test_access", "test_secret")
        set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
        assert any("s3=" in header for header in set_cookies)


def test_logout_deletes_s3_cookie(fastapi_client):
    response = fastapi_client.post("/account/logout", follow_redirects=False)
    assert response.status_code == 303
    set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
    assert any('s3=""' in header or "s3=;" in header for header in set_cookies)


def test_logout_redirects_to_referer(fastapi_client):
    # Same-origin referer (browser sends the full URL) -> back to that path
    response = fastapi_client.post(
        "/account/logout",
        headers={"Referer": "http://testserver/books/OL1M"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["Location"] == "/books/OL1M"

    # Offsite referer -> home, not offsite (legacy web.py redirects raw referer)
    response = fastapi_client.post(
        "/account/logout",
        headers={"Referer": "http://evil.com/phish"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["Location"] == "/"

    # No referer -> home
    response = fastapi_client.post("/account/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["Location"] == "/"


def test_login_error_redirects_to_login_with_flash(fastapi_client):
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email") as mock_get_by_email,
    ):
        mock_audit.return_value = {"error": "account_bad_password"}

        response = fastapi_client.post(
            "/account/login",
            data={"username": "testuser", "password": "wrong", "redirect": "/books"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        location = response.headers["Location"]
        assert location.startswith("/account/login")
        assert "redirect=%2Fbooks" in location
        assert "username=testuser" in location
        mock_get_by_email.assert_not_called()

        set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
        flash = [unquote(header) for header in set_cookies if "flash=" in header]
        assert flash
        assert "Wrong password" in flash[0]


def test_login_without_username_redirects_to_login(fastapi_client):
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=None),
    ):
        mock_audit.return_value = {}
        mock_gen_code.return_value = "token"

        response = fastapi_client.post(
            "/account/login",
            data={"username": "testuser", "password": "password"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["Location"].startswith("/account/login")
        mock_gen_code.assert_not_called()


def test_login_sets_sfw_and_banner_cookies(fastapi_client):
    mock_user = MagicMock()
    mock_user.get_safe_mode.return_value = "yes"
    mock_user.preferences.return_value = {"yrg_banner_pref": "yrg_banner"}
    mock_account = MagicMock()
    mock_account.get_user.return_value = mock_user
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=mock_account) as mock_get_by_email,
    ):
        mock_audit.return_value = {"ol_username": "testuser", "ia_email": "test@example.com"}
        mock_gen_code.return_value = "token"

        response = fastapi_client.post(
            "/account/login",
            data={"username": "testuser", "password": "password"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        mock_get_by_email.assert_called_once_with("testuser")
        set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
        assert any(header.startswith("sfw=yes") for header in set_cookies)
        assert any(header.startswith("yrg_banner=1") for header in set_cookies)


def test_login_follow_action_subscribes_and_flashes(fastapi_client):
    mock_account = MagicMock()
    mock_account.username = "testuser"
    mock_account.get_user.return_value = None
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=mock_account),
        patch(
            "openlibrary.fastapi.account.OpenLibraryAccount.get_by_username",
            return_value={"data": {"displayname": "Some Publisher"}},
        ),
        patch("openlibrary.fastapi.account.PubSub.subscribe") as mock_subscribe,
    ):
        mock_audit.return_value = {"ol_username": "testuser"}
        mock_gen_code.return_value = "token"

        response = fastapi_client.post(
            "/account/login",
            data={"username": "testuser", "password": "password", "action": "follow:publisher"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        mock_subscribe.assert_called_once_with(subscriber="testuser", publisher="publisher")
        set_cookies = [val for key, val in response.headers.multi_items() if key.lower() == "set-cookie"]
        flash = [unquote(header) for header in set_cookies if "flash=" in header]
        assert flash
        assert "following" in flash[0]


def test_login_forwards_s3_headers_to_audit(fastapi_client):
    with (
        patch("openlibrary.fastapi.account.audit_accounts") as mock_audit,
        patch("openlibrary.fastapi.account.generate_login_code_for_user") as mock_gen_code,
        patch("openlibrary.fastapi.account.OpenLibraryAccount.get_by_email", return_value=None),
    ):
        mock_audit.return_value = {"ol_username": "testuser"}
        mock_gen_code.return_value = "token"

        response = fastapi_client.post(
            "/account/login",
            data={"username": "", "password": ""},
            headers={"X-S3-Access": "ak", "X-S3-Secret": "sk"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        _, kwargs = mock_audit.call_args
        assert kwargs["email"] == ""
        assert kwargs["s3_access_key"] == "ak"
        assert kwargs["s3_secret_key"] == "sk"


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
