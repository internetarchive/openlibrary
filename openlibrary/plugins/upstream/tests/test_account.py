import json
import logging
import os
import sys
from unittest import mock

import pytest
import web

from openlibrary.accounts.model import create_link_doc
from openlibrary.utils.request_context import RequestContextVars, req_context

from .. import account
from ..account import account_login, account_verify


def open_test_data(filename):
    """Returns a file handle to file with specified filename inside test_data directory."""
    root = os.path.dirname(__file__)
    fullpath = os.path.join(root, "test_data", filename)
    return open(fullpath, mode="rb")


def test_create_list_doc(wildcard):
    key = "account/foo/verify"
    username = "foo"
    email = "foo@example.com"

    doc = create_link_doc(key, username, email)

    assert doc == {
        "_key": key,
        "_rev": None,
        "type": "account-link",
        "username": username,
        "email": email,
        "code": wildcard,
        "created_on": wildcard,
        "expires_on": wildcard,
    }


@pytest.mark.parametrize(
    ("redirect", "expected"),
    [
        ("/account/books", True),
        ("/account/login", True),
        ("/books", True),
        ("https://evil.example/path", False),
        ("//evil.example/path", False),
        ("/\\evil.example/path", False),
        ("", False),
    ],
)
def test_is_safe_redirect(redirect, expected):
    assert account.is_safe_redirect(redirect) is expected


class TestGoodReadsImport:
    def setup_method(self, method):
        with open_test_data("goodreads_library_export.csv") as reader:
            self.csv_data = reader.read()

        self.expected_books = {
            "0142402494": {
                "Additional Authors": "Florence Lamborn, Louis S. Glanzman",
                "Author": "Astrid Lindgren",
                "Author l-f": "Lindgren, Astrid",
                "Average Rating": "4.13",
                "BCID": "",
                "Binding": "Mass Market Paperback",
                "Book Id": "19302",
                "Bookshelves": "to-read",
                "Bookshelves with positions": "to-read (#2)",
                "Condition": "",
                "Condition Description": "",
                "Date Added": "2020/12/13",
                "Date Read": "",
                "Exclusive Shelf": "to-read",
                "ISBN": "0142402494",
                "ISBN13": "9780142402498",
                "My Rating": "0",
                "My Review": "",
                "Number of Pages": "160",
                "Original Publication Year": "1945",
                "Original Purchase Date": "",
                "Original Purchase Location": "",
                "Owned Copies": "0",
                "Private Notes": "",
                "Publisher": "Puffin Books",
                "Read Count": "0",
                "Recommended By": "",
                "Recommended For": "",
                "Spoiler": "",
                "Title": "Pippi Longstocking (Pippi Långstrump, #1)",
                "Year Published": "2005",
            },
            "0735214484": {
                "Additional Authors": "",
                "Author": "David   Epstein",
                "Author l-f": "Epstein, David",
                "Average Rating": "4.16",
                "BCID": "",
                "Binding": "Hardcover",
                "Book Id": "41795733",
                "Bookshelves": "to-read",
                "Bookshelves with positions": "to-read (#1)",
                "Condition": "",
                "Condition Description": "",
                "Date Added": "2020/12/13",
                "Date Read": "",
                "Exclusive Shelf": "to-read",
                "ISBN": "0735214484",
                "ISBN13": "9780735214484",
                "My Rating": "0",
                "My Review": "",
                "Number of Pages": "352",
                "Original Publication Year": "2019",
                "Original Purchase Date": "",
                "Original Purchase Location": "",
                "Owned Copies": "0",
                "Private Notes": "",
                "Publisher": "Riverhead Books",
                "Read Count": "0",
                "Recommended By": "",
                "Recommended For": "",
                "Spoiler": "",
                "Title": "Range: Why Generalists Triumph in a Specialized World",
                "Year Published": "2019",
            },
        }

        self.expected_books_wo_isbns = {
            "99999999999": {
                "Additional Authors": "",
                "Author": "AuthorWith NoISBN",
                "Author l-f": "NoISBN, AuthorWith",
                "Average Rating": "4.16",
                "BCID": "",
                "Binding": "Hardcover",
                "Book Id": "99999999999",
                "Bookshelves": "to-read",
                "Bookshelves with positions": "to-read (#1)",
                "Condition": "",
                "Condition Description": "",
                "Date Added": "2020/12/13",
                "Date Read": "",
                "Exclusive Shelf": "to-read",
                "ISBN": "",
                "ISBN13": "",
                "My Rating": "0",
                "My Review": "",
                "Number of Pages": "352",
                "Original Publication Year": "2019",
                "Original Purchase Date": "",
                "Original Purchase Location": "",
                "Owned Copies": "0",
                "Private Notes": "",
                "Publisher": "Test Publisher",
                "Read Count": "0",
                "Recommended By": "",
                "Recommended For": "",
                "Spoiler": "",
                "Title": "Test Book Title With No ISBN",
                "Year Published": "2019",
            }
        }

    @pytest.mark.skipif(sys.version_info < (3, 0), reason="Python2's csv module doesn't support Unicode")
    def test_process_goodreads_csv_with_utf8(self):
        books, books_wo_isbns = account.process_goodreads_csv(web.storage({"csv": self.csv_data.decode("utf-8")}))
        assert books == self.expected_books
        assert books_wo_isbns == self.expected_books_wo_isbns

    @pytest.mark.xfail
    def test_process_goodreads_csv_with_bytes(self):
        # Note: In Python2, reading data as bytes returns a string, which should
        # also be supported by account.process_goodreads_csv()
        books, books_wo_isbns = account.process_goodreads_csv(web.storage({"csv": self.csv_data}))
        assert books == self.expected_books
        assert books_wo_isbns == self.expected_books_wo_isbns


# --- account_verify.GET ---


class TestAccountVerify:
    """Tests for the /account/verify GET endpoint."""

    def _make_handler(self):
        return account_verify()

    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.account_login")
    @mock.patch("openlibrary.plugins.upstream.account.add_flash_message")
    @mock.patch("openlibrary.plugins.upstream.account._", lambda x, **kw: x)
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_valid_token_redirects_to_my_books(self, mock_web, mock_flash, mock_login_cls, mock_ia_account):
        mock_web.input.return_value = web.storage(t="validtoken", redirect="")
        mock_ia_account.verify.return_value = {
            "email": "test@example.com",
            "s3": {"access": "ACCESSKEY", "secret": "SECRETKEY"},
        }
        login_instance = mock.MagicMock()
        mock_login_cls.return_value = login_instance

        self._make_handler().GET()

        mock_ia_account.verify.assert_called_once_with(token="validtoken")
        # No explicit redirect is forwarded when the caller didn't request one;
        # account_login.login()'s own fallback sends the user to /account/books
        # without clearing the pending patron-intent cookie.
        login_instance.login.assert_called_once_with(
            access="ACCESSKEY",
            secret="SECRETKEY",
        )

    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.account_login")
    @mock.patch("openlibrary.plugins.upstream.account.add_flash_message")
    @mock.patch("openlibrary.plugins.upstream.account._", lambda x, **kw: x)
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_valid_token_honors_redirect_param(self, mock_web, mock_flash, mock_login_cls, mock_ia_account):
        mock_web.input.return_value = web.storage(t="validtoken", redirect="/works/OL1W")
        mock_ia_account.verify.return_value = {
            "email": "test@example.com",
            "s3": {"access": "ACCESSKEY", "secret": "SECRETKEY"},
        }
        login_instance = mock.MagicMock()
        mock_login_cls.return_value = login_instance

        self._make_handler().GET()

        login_instance.login.assert_called_once_with(
            access="ACCESSKEY",
            secret="SECRETKEY",
            redirect="/works/OL1W",
        )

    @mock.patch("openlibrary.plugins.upstream.account.accounts")
    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.add_flash_message")
    @mock.patch("openlibrary.plugins.upstream.account._", lambda x, **kw: x)
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_invalid_token_redirects_to_create_when_not_logged_in(self, mock_web, mock_flash, mock_ia_account, mock_accounts):
        mock_web.input.return_value = web.storage(t="badtoken", redirect="")
        mock_ia_account.verify.return_value = {"error": "invalid_token"}
        mock_accounts.get_current_user.return_value = None
        mock_web.seeother.side_effect = Exception("redirect")

        with pytest.raises(Exception, match="redirect"):
            self._make_handler().GET()

        mock_flash.assert_called_once()
        assert mock_flash.call_args[0][0] == "error"
        mock_web.seeother.assert_called_once_with("/account/create")

    @mock.patch("openlibrary.plugins.upstream.account.accounts")
    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.add_flash_message")
    @mock.patch("openlibrary.plugins.upstream.account._", lambda x, **kw: x)
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_invalid_token_redirects_to_my_books_when_logged_in(self, mock_web, mock_flash, mock_ia_account, mock_accounts):
        mock_web.input.return_value = web.storage(t="usedtoken", redirect="")
        mock_ia_account.verify.return_value = {"error": "already_verified"}
        mock_accounts.get_current_user.return_value = mock.MagicMock()
        mock_web.seeother.side_effect = Exception("redirect")

        with pytest.raises(Exception, match="redirect"):
            self._make_handler().GET()

        mock_flash.assert_not_called()
        mock_web.seeother.assert_called_once_with("/account/books")

    @mock.patch("openlibrary.plugins.upstream.account.add_flash_message")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_missing_token_redirects_to_create(self, mock_web, mock_flash):
        mock_web.input.return_value = web.storage(t=None, redirect="")
        mock_web.seeother.side_effect = Exception("redirect")

        with pytest.raises(Exception, match="redirect"):
            self._make_handler().GET()

        mock_flash.assert_not_called()
        mock_web.seeother.assert_called_once_with("/account/create")


# --- account_login.login cookie helpers ---


class TestAccountLoginSetCookies:
    """Tests for the set_cookies helper on account_login."""

    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_truthy_value_uses_expires(self, mock_web):
        handler = account_login()
        handler.set_cookies(remember=True, session="abc123")
        mock_web.setcookie.assert_called_once_with("session", "abc123", expires=3600 * 24 * 365)

    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_falsy_value_expires_cookie(self, mock_web):
        handler = account_login()
        handler.set_cookies(remember=True, pda="")
        mock_web.setcookie.assert_called_once_with("pda", "", expires=1)

    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_no_remember_uses_session_expiry(self, mock_web):
        handler = account_login()
        handler.set_cookies(remember=False, session="abc123")
        mock_web.setcookie.assert_called_once_with("session", "abc123", expires="")


class TestAccountLoginRedirect:
    def setup_method(self):
        self._req_context_token = req_context.set(
            RequestContextVars(
                x_forwarded_for=None,
                user_agent="pytest-agent",
                lang="en",
                solr_editions=True,
                print_disabled=False,
                sfw=False,
                is_recognized_bot=False,
                is_bot=False,
            )
        )

    def teardown_method(self):
        req_context.reset(self._req_context_token)

    @mock.patch("openlibrary.plugins.upstream.account.audit_accounts")
    @mock.patch("openlibrary.plugins.upstream.account.OpenLibraryAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    @mock.patch("openlibrary.plugins.upstream.account.stats")
    def test_login_deletes_preserve_intent_cookie_on_valid_redirect(self, mock_stats, mock_web, mock_ol_account_cls, mock_audit_accounts):
        handler = account_login()
        mock_audit_accounts.return_value = {"ia_email": "test@example.com"}
        mock_ol_account_cls.get_by_email.return_value = mock.MagicMock()
        mock_web.seeother.side_effect = Exception("seeother")

        # Case 1: Valid redirect string -> deletes preserve intent cookie
        with pytest.raises(Exception, match="seeother"):
            handler.login(username="test", password="pwd", redirect="/books")
        mock_web.setcookie.assert_any_call("pending_action", "", expires=-1)
        mock_web.seeother.assert_called_with("/books")

        mock_web.reset_mock()

        # Case 2: Invalid redirect string -> redirects to fallback without deleting cookie
        with pytest.raises(Exception, match="seeother"):
            handler.login(username="test", password="pwd", redirect="http://evil.com")
        for call in mock_web.setcookie.call_args_list:
            assert call[0][0] != "pending_action"
        mock_web.seeother.assert_called_with("/account/books")


class TestOtpServiceS3Auth:
    """Tests for S3 key validation on /account/otp/issue and /account/otp/redeem."""

    def _make_web_mock(self, auth_header=""):
        m = mock.MagicMock()
        m.ctx.env = {"HTTP_AUTHORIZATION": auth_header, "HTTP_X_FORWARDED_FOR": "1.2.3.4"}
        m.input.return_value = web.storage(email="test@example.com", ip="1.2.3.4", challenge_url="", sendmail="false", otp="123456")
        m.safestr.side_effect = lambda x: x
        return m

    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_issue_missing_auth_header(self, mock_web, mock_ia):
        mock_web.ctx.env = {}
        result = account.otp_service_issue().POST()
        body = json.loads(result.rawtext)
        assert body["error"] == "missing_or_invalid_authorization"
        mock_ia.s3auth.assert_not_called()

    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_issue_empty_secret_rejected(self, mock_web, mock_ia):
        mock_web.ctx.env = {"HTTP_AUTHORIZATION": "LOW access:"}
        result = account.otp_service_issue().POST()
        body = json.loads(result.rawtext)
        assert body["error"] == "missing_or_invalid_authorization"
        mock_ia.s3auth.assert_not_called()

    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_issue_invalid_keys_rejected(self, mock_web, mock_ia):
        mock_ia.s3auth.return_value = {"error": "invalid_s3keys", "code": 401}
        mock_web.ctx.env = {"HTTP_AUTHORIZATION": "LOW badaccess:badsecret"}
        result = account.otp_service_issue().POST()
        body = json.loads(result.rawtext)
        assert body["error"] == "unauthorized"

    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_issue_auth_service_5xx_returns_specific_error(self, mock_web, mock_ia):
        mock_ia.s3auth.return_value = {"error": "service error", "code": 503}
        mock_web.ctx.env = {"HTTP_AUTHORIZATION": "LOW access:secret"}
        result = account.otp_service_issue().POST()
        body = json.loads(result.rawtext)
        assert body["error"] == "auth_service_unavailable"

    @mock.patch("openlibrary.plugins.upstream.account.OTP")
    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_issue_valid_keys_proceeds(self, mock_web, mock_ia, mock_otp):
        mock_ia.s3auth.return_value = {"success": True, "itemname": "@testuser"}
        mock_web.ctx.env = {
            "HTTP_AUTHORIZATION": "LOW goodaccess:goodsecret",
            "HTTP_X_FORWARDED_FOR": "1.2.3.4",
        }
        mock_web.input.return_value = web.storage(email="test@example.com", ip="1.2.3.4", challenge_url="", sendmail="false")
        mock_otp.generate.return_value = "abc123"
        mock_otp.is_ratelimited.return_value = None
        mock_otp.verify_service.return_value = True
        result = account.otp_service_issue().POST()
        body = json.loads(result.rawtext)
        assert body == {"success": "issued"}

    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_redeem_missing_auth_header(self, mock_web, mock_ia):
        mock_web.ctx.env = {}
        result = account.otp_service_redeem().POST()
        body = json.loads(result.rawtext)
        assert body["error"] == "missing_or_invalid_authorization"
        mock_ia.s3auth.assert_not_called()

    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_redeem_invalid_keys_rejected(self, mock_web, mock_ia):
        mock_ia.s3auth.return_value = {"error": "invalid_s3keys", "code": 401}
        mock_web.ctx.env = {"HTTP_AUTHORIZATION": "LOW bad:creds"}
        result = account.otp_service_redeem().POST()
        body = json.loads(result.rawtext)
        assert body["error"] == "unauthorized"

    @mock.patch("openlibrary.plugins.upstream.account.OTP")
    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_redeem_valid_keys_proceeds(self, mock_web, mock_ia, mock_otp):
        mock_ia.s3auth.return_value = {"success": True, "itemname": "@testuser"}
        mock_web.ctx.env = {
            "HTTP_AUTHORIZATION": "LOW goodaccess:goodsecret",
            "HTTP_X_FORWARDED_FOR": "1.2.3.4",
        }
        mock_web.input.return_value = web.storage(email="test@example.com", ip="1.2.3.4", otp="abc123")
        mock_otp.is_valid.return_value = True
        result = account.otp_service_redeem().POST()
        body = json.loads(result.rawtext)
        assert body == {"success": "redeemed"}


class TestOtpFailuresAreVisible:
    """Every refusal must carry a real HTTP status and a log line.

    These endpoints used to answer `200 {"error": ...}` for every failure. A 200
    is not an exception, so Sentry never saw one; it is not an error status, so
    request logs and the load balancer did not flag it either. Requests also fan
    across ol-web0..3 behind haproxy, so with nothing logged there was no way to
    tell which head served a call or why it refused.
    """

    def _env(self, **extra):
        return {
            "HTTP_AUTHORIZATION": "LOW goodaccess:goodsecret",
            "HTTP_X_FORWARDED_FOR": "1.2.3.4, 10.0.0.9",
            **extra,
        }

    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_missing_auth_is_401(self, mock_web, mock_ia):
        mock_web.ctx.env = {}
        account.otp_service_issue().POST()
        assert mock_web.ctx.status == "401 Unauthorized"

    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_rejected_keys_are_401(self, mock_web, mock_ia):
        mock_ia.s3auth.return_value = {"error": "invalid_s3keys", "code": 401}
        mock_web.ctx.env = self._env()
        account.otp_service_issue().POST()
        assert mock_web.ctx.status == "401 Unauthorized"

    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_auth_service_outage_is_503(self, mock_web, mock_ia):
        """A 5xx from xauthn is our problem, not the caller's — it must not be a
        4xx that tells an integrator to go fix their credentials."""
        mock_ia.s3auth.return_value = {"error": "service error", "code": 503}
        mock_web.ctx.env = self._env()
        account.otp_service_issue().POST()
        assert mock_web.ctx.status == "503 Service Unavailable"

    @mock.patch("openlibrary.plugins.upstream.account.OTP")
    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_missing_service_ip_is_400(self, mock_web, mock_ia, mock_otp):
        """No X-Forwarded-For means no service_ip. Callers hitting a web head
        directly, bypassing nginx, see exactly this."""
        mock_ia.s3auth.return_value = {"success": True}
        mock_web.ctx.env = {"HTTP_AUTHORIZATION": "LOW goodaccess:goodsecret"}
        mock_web.input.return_value = web.storage(email="test@example.com", ip="1.2.3.4", challenge_url="", sendmail="false")
        result = account.otp_service_issue().POST()
        assert mock_web.ctx.status == "400 Bad Request"
        assert json.loads(result.rawtext)["missing_keys"] == ["service_ip"]

    @mock.patch("openlibrary.plugins.upstream.account.OTP")
    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_ratelimit_is_429_and_keeps_its_body(self, mock_web, mock_ia, mock_otp):
        mock_ia.s3auth.return_value = {"success": True}
        mock_web.ctx.env = self._env()
        mock_web.input.return_value = web.storage(email="test@example.com", ip="1.2.3.4", challenge_url="", sendmail="false")
        limit = {"ttl": 60, "key": "otp-client:1.2.3.4:email:test@example.com"}
        mock_otp.is_ratelimited.return_value = {"error": "ratelimit", "ratelimit": limit}
        result = account.otp_service_issue().POST()
        assert mock_web.ctx.status == "429 Too Many Requests"
        # The body shape is unchanged, so existing clients keep working.
        assert json.loads(result.rawtext) == {"error": "ratelimit", "ratelimit": limit}

    @mock.patch("openlibrary.plugins.upstream.account.OTP")
    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_otp_mismatch_is_401(self, mock_web, mock_ia, mock_otp):
        mock_ia.s3auth.return_value = {"success": True}
        mock_web.ctx.env = self._env()
        mock_web.input.return_value = web.storage(email="test@example.com", ip="1.2.3.4", otp="wrong")
        mock_otp.is_valid.return_value = False
        result = account.otp_service_redeem().POST()
        assert mock_web.ctx.status == "401 Unauthorized"
        assert json.loads(result.rawtext) == {"error": "otp_mismatch"}

    @mock.patch("openlibrary.plugins.upstream.account.OTP")
    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_success_sets_no_error_status(self, mock_web, mock_ia, mock_otp):
        mock_ia.s3auth.return_value = {"success": True}
        mock_web.ctx.env = self._env()
        mock_web.input.return_value = web.storage(email="test@example.com", ip="1.2.3.4", challenge_url="", sendmail="false")
        mock_otp.is_ratelimited.return_value = None
        mock_otp.generate.return_value = "abc123"
        result = account.otp_service_issue().POST()
        assert json.loads(result.rawtext) == {"success": "issued"}
        assert not isinstance(mock_web.ctx.status, str), "success must not set an error status"

    @mock.patch("openlibrary.plugins.upstream.account.OTP")
    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_refusal_logs_the_service_ip(self, mock_web, mock_ia, mock_otp, caplog):
        """`service_ip` is an ingredient of the OTP's HMAC, so an issue/redeem
        pair that disagrees about it fails forever with otp_mismatch. Logging it
        is the only way to compare the two across web heads."""
        mock_ia.s3auth.return_value = {"success": True}
        mock_web.ctx.env = self._env()
        mock_web.input.return_value = web.storage(email="test@example.com", ip="1.2.3.4", otp="wrong")
        mock_otp.is_valid.return_value = False
        with caplog.at_level(logging.WARNING, logger="openlibrary.account"):
            account.otp_service_redeem().POST()

        assert "1.2.3.4, 10.0.0.9" in caplog.text
        assert "otp_mismatch" in caplog.text
        assert "redeem" in caplog.text

    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_logs_do_not_contain_the_full_patron_email(self, mock_web, mock_ia, caplog):
        mock_ia.s3auth.return_value = {"error": "invalid_s3keys", "code": 401}
        mock_web.ctx.env = self._env()
        with caplog.at_level(logging.WARNING, logger="openlibrary.account"):
            account.otp_service_issue().POST()
        assert "test@example.com" not in caplog.text

    def test_mask_email(self):
        assert account._mask_email("alice@example.org") == "al***@example.org"
        assert account._mask_email("a@b.c") == "a***@b.c"
        assert account._mask_email("") == "***"
        assert account._mask_email("notanemail") == "***"

    def test_every_error_code_has_a_status(self):
        """A code with no mapping silently degrades to 400. Keep them in step."""
        emitted = {
            "missing_or_invalid_authorization",
            "unauthorized",
            "auth_service_unavailable",
            "missing_keys",
            "challenge_failed",
            "ratelimit",
            "otp_mismatch",
        }
        assert emitted <= set(account.OTP_ERROR_STATUS)


class TestParseLowAuthHeader:
    """Unit tests for the _parse_low_auth_header() module-level helper."""

    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_missing_header_raises(self, mock_web):
        mock_web.ctx.env = {}
        with pytest.raises(ValueError, match="Missing or invalid"):
            account._parse_low_auth_header()

    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_bearer_prefix_rejected(self, mock_web):
        mock_web.ctx.env = {"HTTP_AUTHORIZATION": "Bearer sometoken"}
        with pytest.raises(ValueError, match="Missing or invalid"):
            account._parse_low_auth_header()

    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_no_colon_raises(self, mock_web):
        mock_web.ctx.env = {"HTTP_AUTHORIZATION": "LOW accessonly"}
        with pytest.raises(ValueError, match="Malformed"):
            account._parse_low_auth_header()

    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_empty_secret_raises(self, mock_web):
        mock_web.ctx.env = {"HTTP_AUTHORIZATION": "LOW access:"}
        with pytest.raises(ValueError, match="Empty"):
            account._parse_low_auth_header()

    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_empty_access_raises(self, mock_web):
        mock_web.ctx.env = {"HTTP_AUTHORIZATION": "LOW :secret"}
        with pytest.raises(ValueError, match="Empty"):
            account._parse_low_auth_header()

    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_valid_returns_stripped_tuple(self, mock_web):
        mock_web.ctx.env = {"HTTP_AUTHORIZATION": "LOW  myaccess : mysecret "}
        access, secret = account._parse_low_auth_header()
        assert access == "myaccess"
        assert secret == "mysecret"

    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_colon_in_secret_preserved(self, mock_web):
        # S3 secrets can contain colons; only split on the first one
        mock_web.ctx.env = {"HTTP_AUTHORIZATION": "LOW access:sec:ret"}
        access, secret = account._parse_low_auth_header()
        assert access == "access"
        assert secret == "sec:ret"
