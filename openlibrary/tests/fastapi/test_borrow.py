"""Tests for the FastAPI /borrow endpoint's outcome translation."""

import json
from unittest.mock import patch
from urllib.parse import unquote

from openlibrary.plugins.upstream.borrow import BorrowNotFound, BorrowRedirect


class TestBorrowRoute:
    def test_not_found_returns_404(self, fastapi_client):
        with patch("openlibrary.fastapi.borrow.handle_borrow_async", return_value=BorrowNotFound()):
            response = fastapi_client.get("/books/OL999M/x/borrow", follow_redirects=False)

        assert response.status_code == 404

    def test_redirect_sets_flash_cookie_in_infogami_shape(self, fastapi_client):
        outcome = BorrowRedirect("/books/OL1M/Some_Title", flash=("success", "Returned!"))
        with patch("openlibrary.fastapi.borrow.handle_borrow_async", return_value=outcome):
            response = fastapi_client.get("/books/OL1M/x/borrow", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/books/OL1M/Some_Title"
        # web.py's flash reader percent-decodes the raw cookie value (symmetric
        # with web.setcookie()'s percent-encoding), so this must round-trip the
        # same way rather than being valid JSON directly on the wire.
        assert json.loads(unquote(response.cookies["flash"])) == [{"type": "success", "message": "Returned!"}]

    def test_permanent_redirect_uses_301(self, fastapi_client):
        outcome = BorrowRedirect("/books/OL1M/Some_Title", permanent=True)
        with patch("openlibrary.fastapi.borrow.handle_borrow_async", return_value=outcome):
            response = fastapi_client.get("/books/OL1M/x/borrow", follow_redirects=False)

        assert response.status_code == 301

    def test_clear_login_cookie_deletes_session_cookie(self, fastapi_client):
        outcome = BorrowRedirect("/account/login?redirect=x", clear_login_cookie=True)
        with patch("openlibrary.fastapi.borrow.handle_borrow_async", return_value=outcome):
            response = fastapi_client.get("/books/OL1M/x/borrow", follow_redirects=False)

        assert response.status_code == 303
        set_cookie_headers = response.headers.get_list("set-cookie")
        assert any("session=" in h for h in set_cookie_headers)

    def test_slug_segment_is_ignored(self, fastapi_client):
        """The slug is required by the route (always present in real links --
        the real title slug, or a placeholder like "-"/"x"), but its value
        doesn't affect the lookup key, which is derived from the olid alone."""
        outcome = BorrowRedirect("/some/target")
        with patch("openlibrary.fastapi.borrow.handle_borrow_async", return_value=outcome) as mock_core:
            fastapi_client.get("/books/OL1M/Some_Title/borrow", follow_redirects=False)

        called_key = mock_core.call_args.args[0]
        assert called_key == "/books/OL1M"

    def test_missing_slug_404s(self, fastapi_client):
        """The route requires a slug segment; a bare /books/{olid}/borrow
        (no slug) doesn't match at all."""
        response = fastapi_client.get("/books/OL1M/borrow", follow_redirects=False)

        assert response.status_code == 404

    def test_s3_cookie_is_passed_through(self, fastapi_client):
        """parse_s3_cookie() needs the raw cookie value, and nothing under
        FastAPI can use web.cookies() to get it, so the route reads the "s3"
        cookie itself and passes it through explicitly."""
        outcome = BorrowRedirect("/some/target")
        with patch("openlibrary.fastapi.borrow.handle_borrow_async", return_value=outcome) as mock_core:
            fastapi_client.get(
                "/books/OL1M/x/borrow",
                follow_redirects=False,
                headers={"Cookie": "s3=encrypted-token"},
            )

        assert mock_core.call_args.kwargs["s3_cookie"] == "encrypted-token"
