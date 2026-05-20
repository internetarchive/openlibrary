"""Tests for reading log endpoints — regression checks for #12770.

Uses the fastapi_client fixture which imports ALL routers in production order,
so route conflicts like the one in #12770 are caught.
"""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock


class TestReadingLogRoute:
    """Reading log should not be shadowed by the lists catch-all route."""

    READING_LOG_KEYS: ClassVar[list[str]] = ["want-to-read", "currently-reading", "already-read"]

    def test_reading_log_routes_do_not_return_422(self, fastapi_client, monkeypatch):
        """Each valid reading-log key should reach its handler (not 422)."""
        mock_user = MagicMock()
        mock_user.preferences.return_value.get.return_value = "yes"
        monkeypatch.setattr(
            "openlibrary.fastapi.public_my_books.site",
            _mock_site_context_returning(mock_user),
        )
        monkeypatch.setattr("openlibrary.fastapi.public_my_books.ReadingLog", MagicMock())

        for key in self.READING_LOG_KEYS:
            resp = fastapi_client.get(f"/people/testuser/books/{key}.json")
            assert resp.status_code != 422, f"Bug #12770: got 422 for {key}"
            # If it reaches the reading-log handler with a public user, it returns 200
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code} for {key}"

    def test_private_reading_log_returns_403_not_422(self, fastapi_client, monkeypatch):
        """A private reading log should 403, not 422."""
        mock_user = MagicMock()
        mock_user.preferences.return_value.get.return_value = "no"
        monkeypatch.setattr(
            "openlibrary.fastapi.public_my_books.site",
            _mock_site_context_returning(mock_user),
        )

        resp = fastapi_client.get("/people/testuser/books/want-to-read.json")
        assert resp.status_code != 422
        assert resp.status_code == 403

    def test_nonexistent_user_returns_404_not_422(self, fastapi_client, monkeypatch):
        """Unknown user should 404, not 422."""
        monkeypatch.setattr(
            "openlibrary.fastapi.public_my_books.site",
            _mock_site_context_returning(None),
        )

        resp = fastapi_client.get("/people/nobody/books/want-to-read.json")
        assert resp.status_code != 422
        assert resp.status_code == 404


def _mock_site_context_returning(user):
    """Build a mock 'site' ContextVar whose .get() returns a site-like object.

    The returned mock-site's .get(key) returns *user* so that the reading-log
    handler can look up "/people/{username}".
    """
    mock_site = MagicMock()
    mock_site.get.return_value = user
    mock_context = MagicMock()
    mock_context.get.return_value = mock_site
    return mock_context
