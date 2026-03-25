"""Tests for POST /works/OL{work_id}W/notes (FastAPI)."""

from unittest.mock import patch

import pytest


@pytest.fixture
def mock_booknotes():
    """Prevent real DB calls for Booknotes methods."""
    with (
        patch("openlibrary.core.models.Booknotes.add", autospec=True) as add_mock,
        patch("openlibrary.core.models.Booknotes.remove", autospec=True) as remove_mock,
    ):
        add_mock.return_value = 1
        remove_mock.return_value = 1
        yield add_mock, remove_mock


class TestBooknotesPost:
    """Tests for POST /works/OL{work_id}W/notes."""

    def test_add_note(self, fastapi_client, mock_authenticated_user, mock_booknotes):
        """Add a note: returns 200 and calls Booknotes.add with correct args."""
        add_mock, remove_mock = mock_booknotes
        response = fastapi_client.post(
            "/works/OL123W/notes",
            data={"notes": "Great book!"},
        )
        assert response.status_code == 200
        assert response.json() == {"success": "note added"}
        add_mock.assert_called_once_with(
            username="testuser",
            work_id=123,
            notes="Great book!",
            edition_id=-1,
        )
        remove_mock.assert_not_called()

    def test_add_note_with_edition_id(self, fastapi_client, mock_authenticated_user, mock_booknotes):
        """Add note with edition_id: validates OL format and passes numeric ID."""
        add_mock, _ = mock_booknotes
        response = fastapi_client.post(
            "/works/OL123W/notes",
            data={"notes": "Edition-specific note", "edition_id": "OL456M"},
        )
        assert response.status_code == 200
        add_mock.assert_called_once_with(
            username="testuser",
            work_id=123,
            notes="Edition-specific note",
            edition_id=456,
        )

    def test_add_note_with_lowercase_edition_id(self, fastapi_client, mock_authenticated_user, mock_booknotes):
        """Add note with lowercase edition_id: accepts case-insensitive OL format."""
        add_mock, _ = mock_booknotes
        response = fastapi_client.post(
            "/works/OL123W/notes",
            data={"notes": "Edition-specific note", "edition_id": "ol456m"},
        )
        assert response.status_code == 200
        add_mock.assert_called_once_with(
            username="testuser",
            work_id=123,
            notes="Edition-specific note",
            edition_id=456,
        )

    def test_remove_note(self, fastapi_client, mock_authenticated_user, mock_booknotes):
        """Remove a note: returns 200 and calls Booknotes.remove with correct args."""
        _, remove_mock = mock_booknotes
        response = fastapi_client.post(
            "/works/OL123W/notes",
            data={},
        )
        assert response.status_code == 200
        assert response.json() == {"success": "removed note"}
        remove_mock.assert_called_once_with("testuser", 123, edition_id=-1)

    def test_invalid_edition_id_returns_422(self, fastapi_client, mock_authenticated_user):
        """Invalid edition_id format (not OL{number}M) returns 422 validation error."""
        response = fastapi_client.post(
            "/works/OL123W/notes",
            data={"notes": "Should fail", "edition_id": "invalid"},
        )
        assert response.status_code == 422

    def test_invalid_work_id_returns_422(self, fastapi_client, mock_authenticated_user):
        """Invalid work_id (negative) returns 422 validation error."""
        response = fastapi_client.post(
            "/works/OL-1W/notes",
            data={"notes": "Should fail"},
        )
        assert response.status_code == 422
