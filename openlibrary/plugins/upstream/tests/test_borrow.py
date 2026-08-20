"""Tests for the shared /borrow logic and its legacy web.py adapter."""

from unittest.mock import MagicMock, patch

import pytest
import web

from openlibrary.plugins.upstream import borrow


def _mock_edition(**attrs):
    edition = MagicMock()
    for name, value in attrs.items():
        setattr(edition, name, value)
    return edition


class TestBorrowPostCore:
    def test_not_found(self):
        with patch("openlibrary.plugins.upstream.borrow.site") as mock_site:
            mock_site.get.return_value.get.return_value = None
            result = borrow.borrow_post_core("/books/OL1M", borrow.BorrowParams())

        assert result == borrow.BorrowNotFound()

    def test_locate_action_redirects_to_worldcat(self):
        edition = _mock_edition()
        edition.get_worldcat_url.return_value = "https://search.worldcat.org/title/1"

        with patch("openlibrary.plugins.upstream.borrow.site") as mock_site:
            mock_site.get.return_value.get.return_value = edition
            result = borrow.borrow_post_core("/books/OL1M", borrow.BorrowParams(action="locate"))

        assert result == borrow.BorrowRedirect("https://search.worldcat.org/title/1")

    def test_not_logged_in_redirects_to_login_and_clears_login_cookie(self):
        edition = _mock_edition(ocaid="ocaid123", key="/books/OL1M")
        edition.url.return_value = "/books/OL1M/Some_Title"

        with (
            patch("openlibrary.plugins.upstream.borrow.site") as mock_site,
            patch("openlibrary.book_providers.get_book_provider", return_value=None),
            patch("openlibrary.plugins.upstream.borrow.lending.get_availability_async", return_value={}),
            patch("openlibrary.plugins.upstream.borrow.accounts.get_current_user", return_value=None),
        ):
            mock_site.get.return_value.get.return_value = edition
            result = borrow.borrow_post_core("/books/OL1M", borrow.BorrowParams())

        assert isinstance(result, borrow.BorrowRedirect)
        assert result.clear_login_cookie is True
        assert result.url.startswith("/account/login?redirect=")
        assert "action%3Dborrow" in result.url

    def test_lending_limit_hit_returns_flash_and_redirect_to_key(self):
        user = MagicMock()
        user.has_borrowed.return_value = False
        account = MagicMock(itemname="ia_item")
        edition = _mock_edition(ocaid="ocaid123", key="/books/OL1M")
        edition.url.return_value = "/books/OL1M/Some_Title"

        with (
            patch("openlibrary.plugins.upstream.borrow.site") as mock_site,
            patch("openlibrary.book_providers.get_book_provider", return_value=None),
            patch("openlibrary.plugins.upstream.borrow.lending.get_availability_async", return_value={}),
            patch("openlibrary.plugins.upstream.borrow.accounts.get_current_user", return_value=user),
            patch("openlibrary.plugins.upstream.borrow.OpenLibraryAccount.get_by_email", return_value=account),
            patch("openlibrary.plugins.upstream.borrow.get_s3_keys", return_value={"s3_key": "x"}),
            patch("openlibrary.plugins.upstream.borrow.user_can_borrow_edition_async", return_value="borrow"),
            patch(
                "openlibrary.plugins.upstream.borrow.lending.s3_loan_api_async",
                side_effect=borrow.lending.PatronAccessException,
            ),
        ):
            mock_site.get.return_value.get.return_value = edition
            result = borrow.borrow_post_core("/books/OL1M", borrow.BorrowParams())

        assert isinstance(result, borrow.BorrowRedirect)
        assert result.url == "/books/OL1M"
        assert result.flash is not None
        assert result.flash[0] == "error"


class TestBorrowPostAdapter:
    """Tests the web.py `borrow.POST` translation of outcomes into
    raises/flash-messages/cookies. Mirrors the minimal web.ctx setup used in
    test_account_loans.py's legacy-handler tests."""

    @pytest.fixture(autouse=True)
    def _setup_ctx(self):
        web.ctx.headers = []
        web.ctx.path = "/books/OL1M/borrow"
        web.ctx.home = ""
        web.ctx.realhome = ""
        web.ctx.status = "200 OK"
        web.ctx.query = ""
        web.ctx.env = {"REQUEST_METHOD": "GET", "QUERY_STRING": ""}

    def _post(self, key="/books/OL1M"):
        return borrow.borrow().POST(key)

    def test_not_found_raises_404(self):
        with (
            patch("openlibrary.plugins.upstream.borrow.borrow_post_core", return_value=borrow.BorrowNotFound()),
            pytest.raises(web.webapi.HTTPError),
        ):
            self._post()

        assert web.ctx.status.startswith("404")

    def test_redirect_with_flash_sets_flash_and_seeothers(self):
        outcome = borrow.BorrowRedirect("/books/OL1M/Some_Title", flash=("success", "Returned!"))
        with (
            patch("openlibrary.plugins.upstream.borrow.borrow_post_core", return_value=outcome),
            patch("openlibrary.plugins.upstream.borrow.add_flash_message") as mock_flash,
            pytest.raises(web.webapi.HTTPError),
        ):
            self._post()

        mock_flash.assert_called_once_with("success", "Returned!")
        assert web.ctx.status.startswith("303")

    def test_permanent_redirect_uses_301(self):
        outcome = borrow.BorrowRedirect("/books/OL1M/Some_Title", permanent=True)
        with (
            patch("openlibrary.plugins.upstream.borrow.borrow_post_core", return_value=outcome),
            pytest.raises(web.webapi.HTTPError),
        ):
            self._post()

        assert web.ctx.status.startswith("301")

    def test_clear_login_cookie_calls_setcookie(self):
        outcome = borrow.BorrowRedirect("/account/login?redirect=x", clear_login_cookie=True)
        with (
            patch("openlibrary.plugins.upstream.borrow.borrow_post_core", return_value=outcome),
            patch("openlibrary.plugins.upstream.borrow.web.setcookie") as mock_setcookie,
            pytest.raises(web.webapi.HTTPError),
        ):
            self._post()

        mock_setcookie.assert_called_once()
