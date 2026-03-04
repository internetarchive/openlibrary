"""Tests for the /works/OL{work_id}W/notes booknotes endpoint (FastAPI).

Mirrors the legacy `class booknotes(delegate.page)` in
openlibrary/plugins/openlibrary/api.py
"""

from unittest.mock import patch

import pytest

from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user


@pytest.fixture
def mock_auth_user(fastapi_client):
    """Bypass real cookie auth using FastAPI's dependency_overrides.

    This is the correct FastAPI way to override dependencies in tests.
    Patching the function directly does not work because FastAPI's dependency
    injection system has already wired up the dependency when the app starts.
    So instead we tell the app: 'for this test, replace require_authenticated_user
    with a function that just returns our fake user'.
    """
    fake_user = AuthenticatedUser(
        username="testuser",
        user_key="/people/testuser",
        timestamp="2026-01-01T00:00:00",
    )
    fastapi_client.app.dependency_overrides[require_authenticated_user] = lambda: fake_user
    yield fake_user
    fastapi_client.app.dependency_overrides.clear()


@pytest.fixture
def mock_booknotes_add():
    """Prevent real DB calls for Booknotes.add."""
    with patch("openlibrary.core.models.Booknotes.add", autospec=True) as mock:
        mock.return_value = 1
        yield mock


@pytest.fixture
def mock_booknotes_remove():
    """Prevent real DB calls for Booknotes.remove."""
    with patch("openlibrary.core.models.Booknotes.remove", autospec=True) as mock:
        mock.return_value = 1
        yield mock


class TestBooknotesPost:
    """Tests for POST /works/OL{work_id}W/notes."""

    def test_add_note_returns_200(self, fastapi_client, mock_auth_user, mock_booknotes_add):
        """Adding a note returns 200 with success message."""
        response = fastapi_client.post(
            "/works/OL123W/notes",
            data={"notes": "Great book!"},
        )
        assert response.status_code == 200
        assert response.json() == {"success": "note added"}

    def test_remove_note_returns_200(self, fastapi_client, mock_auth_user, mock_booknotes_remove):
        """Posting without notes removes the note and returns 200."""
        response = fastapi_client.post(
            "/works/OL123W/notes",
            data={},
        )
        assert response.status_code == 200
        assert response.json() == {"success": "removed note"}

    def test_add_note_calls_booknotes_add_with_correct_args(self, fastapi_client, mock_auth_user, mock_booknotes_add):
        """Booknotes.add is called with the correct arguments."""
        fastapi_client.post(
            "/works/OL123W/notes",
            data={"notes": "A wonderful read."},
        )
        mock_booknotes_add.assert_called_once_with(
            username="testuser",
            work_id=123,
            notes="A wonderful read.",
            edition_id=-1,
        )

    def test_remove_note_calls_booknotes_remove_with_correct_args(self, fastapi_client, mock_auth_user, mock_booknotes_remove):
        """Booknotes.remove is called with the correct arguments."""
        fastapi_client.post(
            "/works/OL123W/notes",
            data={},
        )
        mock_booknotes_remove.assert_called_once_with("testuser", 123, edition_id=-1)

    def test_add_note_with_edition_id(self, fastapi_client, mock_auth_user, mock_booknotes_add):
        """edition_id is parsed from OL format (OL456M -> 456) and passed correctly."""
        fastapi_client.post(
            "/works/OL123W/notes",
            data={"notes": "Edition-specific note", "edition_id": "OL456M"},
        )
        mock_booknotes_add.assert_called_once_with(
            username="testuser",
            work_id=123,
            notes="Edition-specific note",
            edition_id=456,
        )

    def test_unauthenticated_returns_401(self, fastapi_client):
        """Requests without a valid session cookie return 401.

        No mock_auth_user fixture here — so the real auth runs and
        rejects the request because there is no session cookie.
        The legacy code did a browser redirect to /account/login.
        The FastAPI version correctly returns 401 for a JSON API instead.
        """
        response = fastapi_client.post(
            "/works/OL123W/notes",
            data={"notes": "Should fail"},
        )
        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("work_id", "note"),
        [
            ("1", "Short note"),
            ("99999999", "Note for a large work ID"),
            ("42", "Another note"),
        ],
    )
    def test_various_work_ids_and_notes(self, fastapi_client, mock_auth_user, mock_booknotes_add, work_id, note):
        """Various work IDs and note contents are all handled correctly."""
        response = fastapi_client.post(
            f"/works/OL{work_id}W/notes",
            data={"notes": note},
        )
        assert response.status_code == 200
        assert response.json() == {"success": "note added"}

    def test_db_error_returns_502(self, fastapi_client, mock_auth_user):
        """Database failures return 502 Bad Gateway instead of a raw crash."""
        with patch(
            "openlibrary.core.models.Booknotes.add",
            side_effect=Exception("DB is down"),
        ):
            response = fastapi_client.post(
                "/works/OL123W/notes",
                data={"notes": "This will fail"},
            )
        assert response.status_code == 502
