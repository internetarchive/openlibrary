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
    def test_valid_token_calls_login_with_s3_keys(self, mock_web, mock_flash, mock_login_cls, mock_ia_account):
        mock_web.input.return_value = web.storage(t="validtoken")
        mock_ia_account.verify.return_value = {
            "email": "test@example.com",
            "s3": {"access": "ACCESSKEY", "secret": "SECRETKEY"},
        }
        login_instance = mock.MagicMock()
        mock_login_cls.return_value = login_instance

        self._make_handler().GET()

        mock_ia_account.verify.assert_called_once_with(token="validtoken")
        login_instance.login.assert_called_once_with(
            access="ACCESSKEY",
            secret="SECRETKEY",
        )

    @mock.patch("openlibrary.plugins.upstream.account.InternetArchiveAccount")
    @mock.patch("openlibrary.plugins.upstream.account.add_flash_message")
    @mock.patch("openlibrary.plugins.upstream.account._", lambda x, **kw: x)
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_invalid_token_redirects_to_create(self, mock_web, mock_flash, mock_ia_account):
        mock_web.input.return_value = web.storage(t="badtoken")
        mock_ia_account.verify.return_value = {"error": "invalid_token"}
        mock_web.seeother.side_effect = Exception("redirect")

        with pytest.raises(Exception, match="redirect"):
            self._make_handler().GET()

        mock_flash.assert_called_once()
        flash_args = mock_flash.call_args[0]
        assert flash_args[0] == "error"
        mock_web.seeother.assert_called_once_with("/account/create")

    @mock.patch("openlibrary.plugins.upstream.account.add_flash_message")
    @mock.patch("openlibrary.plugins.upstream.account.web")
    def test_missing_token_redirects_to_create(self, mock_web, mock_flash):
        mock_web.input.return_value = web.storage(t=None)
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


class TestAccountPreferences:
    """Test the account_preferences endpoint"""

    def test_valid_preferences_redirect(self):
        """Test valid preferences update with redirect=True (default) triggers seeother"""
        import json
        from unittest import mock

        prefs = {
            'mode': 'fulltext',
            'language': 'es',
            'date': [2000, 2020],
        }

        with (
            mock.patch('openlibrary.plugins.upstream.account.web.data') as mock_data,
            mock.patch('openlibrary.plugins.upstream.account.web.setcookie'),
            mock.patch(
                'openlibrary.plugins.upstream.account.web.seeother',
                side_effect=Exception,
            ),
        ):
            mock_data.return_value = json.dumps(prefs).encode()
            handler = account.account_preferences()

            with pytest.raises(Exception, match='.*'):
                handler.POST()

            # Verify cookies were set before redirect
            assert mock_data.called

    def test_valid_preferences_json_response(self):
        """Test valid preferences update with redirect=False returning JSON"""
        import json
        from unittest import mock

        prefs = {
            'mode': 'preview',
            'language': 'fr',
            'date': [1999, 2025],
            'redirect': False,
        }

        with (
            mock.patch('openlibrary.plugins.upstream.account.web.data') as mock_data,
            mock.patch('openlibrary.plugins.upstream.account.web.setcookie'),
        ):
            mock_data.return_value = json.dumps(prefs).encode()
            handler = account.account_preferences()
            response = handler.POST()

            # Should return JSON with backend_prefs
            result = json.loads(response.rawtext)
            assert result['status'] == 'ok'
            assert result['backend_prefs']['formats'] == 'ebook_access'
            assert result['backend_prefs']['languages'] == ['fr']

    def test_mode_transformation_fulltext(self):
        """Test mode='fulltext' transforms to formats='has_fulltext'"""
        import json
        from unittest import mock

        prefs = {
            'mode': 'fulltext',
            'language': 'all',
            'date': [1900, 2025],
            'redirect': False,
        }

        with (
            mock.patch('openlibrary.plugins.upstream.account.web.data') as mock_data,
            mock.patch('openlibrary.plugins.upstream.account.web.setcookie'),
        ):
            mock_data.return_value = json.dumps(prefs).encode()
            handler = account.account_preferences()
            response = handler.POST()

            result = json.loads(response.rawtext)
            assert result['backend_prefs']['formats'] == 'has_fulltext'

    def test_mode_transformation_preview(self):
        """Test mode='preview' transforms to formats='ebook_access'"""
        import json
        from unittest import mock

        prefs = {
            'mode': 'preview',
            'language': 'all',
            'date': [1900, 2025],
            'redirect': False,
        }

        with (
            mock.patch('openlibrary.plugins.upstream.account.web.data') as mock_data,
            mock.patch('openlibrary.plugins.upstream.account.web.setcookie'),
        ):
            mock_data.return_value = json.dumps(prefs).encode()
            handler = account.account_preferences()
            response = handler.POST()

            result = json.loads(response.rawtext)
            assert result['backend_prefs']['formats'] == 'ebook_access'

    def test_mode_transformation_all(self):
        """Test mode='all' transforms to formats=None"""
        import json
        from unittest import mock

        prefs = {
            'mode': 'all',
            'language': 'all',
            'date': [1900, 2025],
            'redirect': False,
        }

        with (
            mock.patch('openlibrary.plugins.upstream.account.web.data') as mock_data,
            mock.patch('openlibrary.plugins.upstream.account.web.setcookie'),
        ):
            mock_data.return_value = json.dumps(prefs).encode()
            handler = account.account_preferences()
            response = handler.POST()

            result = json.loads(response.rawtext)
            assert result['backend_prefs']['formats'] is None

    def test_language_all_omitted_from_backend_prefs(self):
        """Test that language='all' is omitted from backend_prefs"""
        import json
        from unittest import mock

        prefs = {
            'mode': 'all',
            'language': 'all',
            'date': [1900, 2025],
            'redirect': False,
        }

        with (
            mock.patch('openlibrary.plugins.upstream.account.web.data') as mock_data,
            mock.patch('openlibrary.plugins.upstream.account.web.setcookie'),
        ):
            mock_data.return_value = json.dumps(prefs).encode()
            handler = account.account_preferences()
            response = handler.POST()

            result = json.loads(response.rawtext)
            assert 'languages' not in result['backend_prefs']

    def test_language_specific_wrapped_in_list(self):
        """Test that specific language is wrapped in a list"""
        import json
        from unittest import mock

        prefs = {
            'mode': 'all',
            'language': 'de',
            'date': [1900, 2025],
            'redirect': False,
        }

        with (
            mock.patch('openlibrary.plugins.upstream.account.web.data') as mock_data,
            mock.patch('openlibrary.plugins.upstream.account.web.setcookie'),
        ):
            mock_data.return_value = json.dumps(prefs).encode()
            handler = account.account_preferences()
            response = handler.POST()

            result = json.loads(response.rawtext)
            assert result['backend_prefs']['languages'] == ['de']

    def test_invalid_json(self):
        """Test handling of invalid JSON"""
        import json
        from unittest import mock

        with (
            mock.patch('openlibrary.plugins.upstream.account.web.data') as mock_data,
            mock.patch('openlibrary.plugins.upstream.account.web.setcookie'),
        ):
            mock_data.return_value = b'invalid json {'
            handler = account.account_preferences()
            response = handler.POST()

            result = json.loads(response.rawtext)
            assert 'error' in result

    def test_missing_fields_use_defaults(self):
        """Test that missing fields use default values"""
        import json
        from unittest import mock

        prefs = {'mode': 'fulltext', 'redirect': False}  # Missing language and date

        with (
            mock.patch('openlibrary.plugins.upstream.account.web.data') as mock_data,
            mock.patch('openlibrary.plugins.upstream.account.web.setcookie'),
        ):
            mock_data.return_value = json.dumps(prefs).encode()
            handler = account.account_preferences()
            response = handler.POST()

            result = json.loads(response.rawtext)
            assert result['status'] == 'ok'
            # Verify defaults were used
            assert result['backend_prefs']['first_publish_year'] == [1900, 2025]

    def test_date_range_passthrough(self):
        """Test that date range is passed through directly"""
        import json
        from unittest import mock

        date_range = [2010, 2023]
        prefs = {
            'mode': 'all',
            'language': 'all',
            'date': date_range,
            'redirect': False,
        }

        with (
            mock.patch('openlibrary.plugins.upstream.account.web.data') as mock_data,
            mock.patch('openlibrary.plugins.upstream.account.web.setcookie'),
        ):
            mock_data.return_value = json.dumps(prefs).encode()
            handler = account.account_preferences()
            response = handler.POST()

            result = json.loads(response.rawtext)
            assert result['backend_prefs']['first_publish_year'] == date_range

    def test_cookies_expire_in_one_year(self):
        """Test that cookies are set with 1-year expiration"""
        import json
        from unittest import mock

        prefs = {
            'mode': 'fulltext',
            'language': 'en',
            'date': [2000, 2020],
            'redirect': False,
        }

        with (
            mock.patch('openlibrary.plugins.upstream.account.web.data') as mock_data,
            mock.patch(
                'openlibrary.plugins.upstream.account.web.setcookie'
            ) as mock_setcookie,
        ):
            mock_data.return_value = json.dumps(prefs).encode()
            handler = account.account_preferences()
            handler.POST()

            # Verify expires time is 1 year (3600 * 24 * 365)
            calls = mock_setcookie.call_args_list
            for call in calls:
                assert 'expires' in call.kwargs
                assert call.kwargs['expires'] == 3600 * 24 * 365
