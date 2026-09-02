"""Tests for FastAPI account endpoints."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

from PIL import Image

from openlibrary.core.auth import ExpiredTokenError, MissingKeyError
from openlibrary.fastapi.account import sanitize_image
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

        # Case 2: Invalid/unsafe redirect -> does not delete cookie, redirects to home /
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


class TestAvatarUpload:
    def test_upload_avatar_unauthenticated(self, fastapi_client):
        response = fastapi_client.post("/account/avatar")
        assert response.status_code == 401

    def test_upload_avatar_success(self, fastapi_client, mock_authenticated_user, monkeypatch):
        # Create a small valid test JPEG image using Pillow
        img = Image.new("RGB", (100, 100), color="blue")
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="JPEG")
        img_bytes = img_byte_arr.getvalue()

        # Mock OpenLibraryAccount.get_by_username
        mock_account = {
            "internetarchive_itemname": "@testuser-archive",
            "username": "testuser",
            "s3_keys": {"access": "mock_access", "secret": "mock_secret"},
        }
        monkeypatch.setattr(
            "openlibrary.accounts.OpenLibraryAccount.get_by_username",
            lambda username: mock_account,
        )

        # Mock site store; get_avatar_url will find no user doc and fall back
        # to the "@{username}" itemname convention.
        mock_site = MagicMock()
        mock_site.store = {"account/testuser": mock_account}
        mock_site.get.return_value = None
        site.set(mock_site)

        # get_avatar_url is memoized with a computed memcache key; patch the
        # underlying client so the invalidation delete can be observed.
        mock_memcache = MagicMock()
        mock_memcache.get.return_value = None
        monkeypatch.setattr("openlibrary.core.cache.memcache_cache.memcache", mock_memcache)

        response = fastapi_client.post(
            "/account/avatar",
            files={"file": ("test_avatar.jpg", img_bytes, "image/jpeg")},
        )

        print("DEBUG BODY:", response.text)
        data = response.json()
        assert data["status"] == "success"
        assert data["avatar_url"] == "https://archive.org/services/img/@testuser"
        assert any(call.args and call.args[0] == "user-avatar-testuser" for call in mock_memcache.delete.call_args_list)
        assert mock_account["avatar_updated"]

    def test_upload_avatar_exif_orientation_is_baked_in(self, fastapi_client, mock_authenticated_user, monkeypatch):
        """A photo flagged as rotated by EXIF is re-encoded upright."""
        mock_account = {
            "internetarchive_itemname": "@testuser-archive",
            "username": "testuser",
            "s3_keys": {"access": "mock_access", "secret": "mock_secret"},
        }
        monkeypatch.setattr(
            "openlibrary.accounts.OpenLibraryAccount.get_by_username",
            lambda username: mock_account,
        )

        mock_site = MagicMock()
        mock_site.store = {"account/testuser": mock_account}
        mock_site.get.return_value = None
        site.set(mock_site)

        mock_memcache = MagicMock()
        mock_memcache.get.return_value = None
        monkeypatch.setattr("openlibrary.core.cache.memcache_cache.memcache", mock_memcache)

        # A wide image with EXIF orientation 6 (rotate 90 CW) should decode as
        # tall after sanitize_image bakes the orientation into the pixels.
        img = Image.new("RGB", (200, 100), color="red")
        buf = io.BytesIO()
        exif = Image.Exif()
        exif[0x0112] = 6  # Orientation: rotate 90 CW
        img.save(buf, format="JPEG", exif=exif)

        out = Image.open(sanitize_image(buf.getvalue(), "testuser"))
        assert out.size == (100, 200)

    def test_upload_avatar_invalid_file_type(self, fastapi_client, mock_authenticated_user, monkeypatch):
        mock_account = {
            "internetarchive_itemname": "@testuser-archive",
            "username": "testuser",
        }
        monkeypatch.setattr(
            "openlibrary.accounts.OpenLibraryAccount.get_by_username",
            lambda username: mock_account,
        )

        response = fastapi_client.post(
            "/account/avatar",
            files={"file": ("test.txt", b"not an image file content", "text/plain")},
        )

        assert response.status_code == 400
        assert "Invalid or corrupt image file" in response.json()["detail"]

    def test_upload_avatar_file_too_large(self, fastapi_client, mock_authenticated_user, monkeypatch):
        mock_account = {
            "internetarchive_itemname": "@testuser-archive",
            "username": "testuser",
        }
        monkeypatch.setattr(
            "openlibrary.accounts.OpenLibraryAccount.get_by_username",
            lambda username: mock_account,
        )

        large_bytes = b"x" * (6 * 1024 * 1024)  # 6 MB

        response = fastapi_client.post(
            "/account/avatar",
            files={"file": ("large.jpg", large_bytes, "image/jpeg")},
        )

        assert response.status_code == 400
        assert "File size exceeds 5MB limit" in response.json()["detail"]

    def test_delete_avatar_unauthenticated(self, fastapi_client):
        response = fastapi_client.delete("/account/avatar")
        assert response.status_code == 401

    def test_delete_avatar_success(self, fastapi_client, mock_authenticated_user, monkeypatch):
        mock_account = {
            "internetarchive_itemname": "@testuser-archive",
            "username": "testuser",
            "avatar_updated": 1234567,
        }
        mock_site = MagicMock()
        mock_site.store = {"account/testuser": mock_account}
        mock_site.get.return_value = None
        site.set(mock_site)

        mock_memcache = MagicMock()
        mock_memcache.get.return_value = None
        monkeypatch.setattr("openlibrary.core.cache.memcache_cache.memcache", mock_memcache)

        response = fastapi_client.delete("/account/avatar")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["message"] == "Profile picture removed successfully"
        assert "avatar_updated" not in mock_account
        assert any(call.args and call.args[0] == "user-avatar-testuser" for call in mock_memcache.delete.call_args_list)

    def test_delete_avatar_no_avatar_exists(self, fastapi_client, mock_authenticated_user, monkeypatch):
        mock_account = {
            "internetarchive_itemname": "@testuser-archive",
            "username": "testuser",
        }
        mock_site = MagicMock()
        mock_site.store = {"account/testuser": mock_account}
        site.set(mock_site)

        response = fastapi_client.delete("/account/avatar")

        assert response.status_code == 400
        assert "No custom profile picture exists to remove" in response.json()["detail"]
