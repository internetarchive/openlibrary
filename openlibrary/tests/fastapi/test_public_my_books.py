"""Tests for reading log endpoints — regression checks for #12770.

Uses the fastapi_client fixture which imports ALL routers in production order,
so route conflicts like the one in #12770 are caught.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


class TestReadingLogRoute:
    """Reading log should not be shadowed by the lists catch-all route."""

    def test_want_to_read_route_returns_200(self, fastapi_client, monkeypatch):
        mock_user = MagicMock()
        mock_user.preferences.return_value.get.return_value = "yes"
        monkeypatch.setattr(
            "openlibrary.fastapi.public_my_books.site",
            _mock_site_context_returning(mock_user),
        )
        mock_reading_log = MagicMock()
        mock_reading_log_instance = mock_reading_log.return_value
        mock_reading_log_instance.get_works_async = AsyncMock(return_value=MagicMock(docs=[]))
        mock_reading_log_instance.count_shelf = MagicMock(return_value=0)
        monkeypatch.setattr("openlibrary.fastapi.public_my_books.ReadingLog", mock_reading_log)

        resp = fastapi_client.get("/people/testuser/books/want-to-read.json")
        # If it reaches the reading-log handler with a public user, it returns 200
        assert resp.status_code == 200

    def test_private_reading_log_returns_403(self, fastapi_client, monkeypatch):
        mock_user = MagicMock()
        mock_user.preferences.return_value.get.return_value = "no"
        monkeypatch.setattr(
            "openlibrary.fastapi.public_my_books.site",
            _mock_site_context_returning(mock_user),
        )

        resp = fastapi_client.get("/people/testuser/books/want-to-read.json")
        assert resp.status_code == 403

    def test_nonexistent_user_returns_404(self, fastapi_client, monkeypatch):
        monkeypatch.setattr(
            "openlibrary.fastapi.public_my_books.site",
            _mock_site_context_returning(None),
        )

        resp = fastapi_client.get("/people/nobody/books/want-to-read.json")
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
