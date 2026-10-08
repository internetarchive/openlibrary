"""Tests for the shared /borrow logic and its legacy web.py adapter."""

from unittest.mock import MagicMock, patch

import pytest
import web
from markupsafe import Markup

from openlibrary.book_providers import Acquisition, AcquisitionAccessLiteral
from openlibrary.core.jinja import render_jinja_template
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
            result = borrow.handle_borrow("/books/OL1M", borrow.BorrowParams(), s3_cookie=None)

        assert result == borrow.BorrowNotFound()

    def test_locate_action_redirects_to_worldcat(self):
        edition = _mock_edition()
        edition.get_worldcat_url.return_value = "https://search.worldcat.org/title/1"

        with patch("openlibrary.plugins.upstream.borrow.site") as mock_site:
            mock_site.get.return_value.get.return_value = edition
            result = borrow.handle_borrow("/books/OL1M", borrow.BorrowParams(action="locate"), s3_cookie=None)

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
            result = borrow.handle_borrow("/books/OL1M", borrow.BorrowParams(), s3_cookie=None)

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
            patch("openlibrary.plugins.upstream.borrow.parse_s3_cookie", return_value={"s3_key": "x"}),
            patch("openlibrary.plugins.upstream.borrow.user_can_borrow_edition_async", return_value="borrow"),
            patch(
                "openlibrary.plugins.upstream.borrow.lending.s3_loan_api_async",
                side_effect=borrow.lending.PatronAccessException,
            ),
        ):
            mock_site.get.return_value.get.return_value = edition
            result = borrow.handle_borrow("/books/OL1M", borrow.BorrowParams(), s3_cookie=None)

        assert isinstance(result, borrow.BorrowRedirect)
        assert result.url == "/books/OL1M"
        assert result.flash is not None
        assert result.flash[0] == "error"


class TestProviderBorrow:
    """A provider that lends its own copies (Lenny, #13686).

    `handle_borrow` forwarded only `open-access` acquisitions to their
    provider. A `borrow` one fell through to the Internet Archive branch, which
    has no identifier to work with on a non-IA edition -- so the patron reached
    a bare `archive.org/stream/` instead of the library holding the book.
    """

    @staticmethod
    def _lenny(access: AcquisitionAccessLiteral, url: str):
        provider = MagicMock()
        provider.short_name = "lenny"
        provider.get_acquisitions.return_value = [Acquisition(access=access, format="web", price=None, url=url, provider_name="lenny")]
        return provider

    BORROW_URL = "https://lennyforlibraries.org/v1/api/items/46539165/borrow"

    def _handle(self, provider, action="borrow"):
        edition = _mock_edition(ocaid=None, key="/books/OL46539165M")
        with (
            patch("openlibrary.plugins.upstream.borrow.site") as mock_site,
            patch("openlibrary.book_providers.get_book_provider", return_value=provider),
            patch("openlibrary.plugins.upstream.borrow.render_jinja_template") as mock_render,
        ):
            mock_site.get.return_value.get.return_value = edition
            borrow.handle_borrow("/books/OL46539165M", borrow.BorrowParams(action=action), s3_cookie=None)
        return mock_render

    def test_a_borrow_acquisition_is_forwarded_to_the_provider(self):
        mock_render = self._handle(self._lenny("borrow", self.BORROW_URL))
        mock_render.assert_called_once()
        assert mock_render.call_args.kwargs["url"] == self.BORROW_URL

    def test_an_open_access_acquisition_is_still_forwarded(self):
        url = "https://lennyforlibraries.org/v1/api/items/37044817/read"
        mock_render = self._handle(self._lenny("open-access", url), action="read")
        assert mock_render.call_args.kwargs["url"] == url


class TestMediatedProviderBorrow:
    """A borrow Open Library runs itself rather than handing off (#13688).

    The difference is one kwarg to one template, and it is the difference
    between the patron finishing on the book page they started on and
    finishing on another library's website.
    """

    BORROW_URL = "https://lennyforlibraries.org/v1/api/items/46539165/borrow"
    MEDIATED_URL = "/borrow/lenny/OL46539165M"

    @staticmethod
    def _provider(access: AcquisitionAccessLiteral = "borrow"):
        provider = MagicMock()
        provider.short_name = "lenny"
        provider.get_acquisitions.return_value = [
            Acquisition(
                access=access,
                format="web",
                price=None,
                url=TestMediatedProviderBorrow.BORROW_URL,
                provider_name="lenny",
            )
        ]
        return provider

    def _handle(self, provider, mediated, action="borrow"):
        edition = _mock_edition(ocaid=None, key="/books/OL46539165M")
        with (
            patch("openlibrary.plugins.upstream.borrow.site") as mock_site,
            patch("openlibrary.book_providers.get_book_provider", return_value=provider),
            patch("openlibrary.plugins.upstream.borrow.render_jinja_template") as mock_render,
            patch("openlibrary.plugins.upstream.lenny.mediated_borrow", return_value=mediated) as mock_mediated,
        ):
            mock_site.get.return_value.get.return_value = edition
            borrow.handle_borrow("/books/OL46539165M", borrow.BorrowParams(action=action), s3_cookie=None)
        return mock_render, mock_mediated

    def test_a_configured_node_sends_the_patron_through_open_library(self):
        mock_render, _ = self._handle(self._provider(), (self.MEDIATED_URL, "Archive Labs Lenny"))
        assert mock_render.call_args.kwargs["url"] == self.MEDIATED_URL
        assert mock_render.call_args.kwargs["borrowing"] is True

    def test_the_library_is_named_from_the_node_not_the_feed_provider(self):
        """ "Lenny" is the software. The sentence the patron reads names the
        library, and only the node's own config knows what that is."""
        mock_render, _ = self._handle(self._provider(), (self.MEDIATED_URL, "Archive Labs Lenny"))
        assert "Archive Labs Lenny" in str(mock_render.call_args.kwargs["book_provider"])

    def test_an_unconfigured_node_still_reaches_its_own_sign_in(self):
        """#13686's behaviour, unchanged: no credentials means the node's own
        sign-in, which completes a loan with nothing built on this side."""
        mock_render, _ = self._handle(self._provider(), None)
        assert mock_render.call_args.kwargs["url"] == self.BORROW_URL
        assert mock_render.call_args.kwargs["borrowing"] is False

    def test_an_open_access_title_is_never_routed_through_the_handshake(self):
        """There is no loan to create, so there is nothing to authorize. Asking
        at all would be a database read on every Read button."""
        mock_render, mock_mediated = self._handle(
            self._provider("open-access"),
            (self.MEDIATED_URL, "Archive Labs Lenny"),
            action="read",
        )
        mock_mediated.assert_not_called()
        assert mock_render.call_args.kwargs["borrowing"] is False


class TestInterstitialWording:
    """The one screen that explains the relationship, so it has to be right.

    The two wordings say opposite things -- "a third party we are handing you
    to" against "a trusted provider, and you are not going anywhere" -- and
    which one renders is decided by a single boolean. Nothing else in the
    request distinguishes them.
    """

    LIBRARY = Markup("<strong>Archive Labs Lenny</strong>")

    def _render(self, borrowing, url="/borrow/lenny/OL46539165M"):
        return render_jinja_template(
            "interstitial.html.jinja",
            url=url,
            book_provider=self.LIBRARY,
            wait=5,
            fastapi=False,
            borrowing=borrowing,
        )

    @pytest.fixture(autouse=True)
    def context(self, request_context_fixture):
        request_context_fixture(lang="en")

    def test_a_mediated_borrow_names_the_library_as_a_trusted_provider(self):
        html = self._render(borrowing=True)
        assert "borrowable for free from <strong>Archive Labs Lenny</strong>" in html
        assert "trusted Open Library book provider" in html

    def test_a_mediated_borrow_does_not_call_the_library_a_third_party(self):
        assert "third-party" not in self._render(borrowing=True)

    def test_a_mediated_borrow_shows_no_destination(self):
        """The destination is an openlibrary.org path. Printing it invites the
        question the whole screen exists to answer.

        Shown, not absent: it stays in `data-url` and in the Continue link's
        `href`, which is how the patron gets there at all.
        """
        html = self._render(borrowing=True)
        assert ">/borrow/lenny/OL46539165M<" not in html
        assert 'data-url="/borrow/lenny/OL46539165M"' in html

    def test_a_hand_off_still_warns_that_the_book_is_elsewhere(self):
        """#13690's path, and every other Trusted Book Provider: unchanged."""
        html = self._render(borrowing=False, url="https://standardebooks.org/x")
        assert "third-party Open Library Trusted Book Provider" in html
        assert 'href="https://standardebooks.org/x"' in html


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
            patch("openlibrary.plugins.upstream.borrow.handle_borrow", return_value=borrow.BorrowNotFound()),
            pytest.raises(web.webapi.HTTPError),
        ):
            self._post()

        assert web.ctx.status.startswith("404")

    def test_redirect_with_flash_sets_flash_and_seeothers(self):
        outcome = borrow.BorrowRedirect("/books/OL1M/Some_Title", flash=("success", "Returned!"))
        with (
            patch("openlibrary.plugins.upstream.borrow.handle_borrow", return_value=outcome),
            patch("openlibrary.plugins.upstream.borrow.add_flash_message") as mock_flash,
            pytest.raises(web.webapi.HTTPError),
        ):
            self._post()

        mock_flash.assert_called_once_with("success", "Returned!")
        assert web.ctx.status.startswith("303")

    def test_permanent_redirect_uses_301(self):
        outcome = borrow.BorrowRedirect("/books/OL1M/Some_Title", permanent=True)
        with (
            patch("openlibrary.plugins.upstream.borrow.handle_borrow", return_value=outcome),
            pytest.raises(web.webapi.HTTPError),
        ):
            self._post()

        assert web.ctx.status.startswith("301")

    def test_clear_login_cookie_calls_setcookie(self):
        outcome = borrow.BorrowRedirect("/account/login?redirect=x", clear_login_cookie=True)
        with (
            patch("openlibrary.plugins.upstream.borrow.handle_borrow", return_value=outcome),
            patch("openlibrary.plugins.upstream.borrow.web.setcookie") as mock_setcookie,
            pytest.raises(web.webapi.HTTPError),
        ):
            self._post()

        mock_setcookie.assert_called_once()
