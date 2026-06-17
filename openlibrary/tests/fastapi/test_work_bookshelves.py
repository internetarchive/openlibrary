"""Tests for the FastAPI work bookshelves endpoints."""

import json
from unittest.mock import patch

import pytest
import web

from openlibrary.plugins.openlibrary.api import work_bookshelves as legacy_work_bookshelves


class FakeLegacyUser:
    def __init__(self, username: str = "testuser"):
        self.key = f"/people/{username}"


def mock_web_input_func(data):
    def _mock_web_input(*args, **kwargs):
        return web.storage(kwargs | data)

    return _mock_web_input


def legacy_bookshelves_json(data, work_id=123):
    with (
        patch("openlibrary.plugins.openlibrary.api.web.input", side_effect=mock_web_input_func(data)),
        patch("openlibrary.accounts.get_current_user", return_value=FakeLegacyUser()),
        pytest.deprecated_call(match="migrated to fastapi"),
    ):
        return json.loads(legacy_work_bookshelves().POST(str(work_id))["rawtext"])


@pytest.fixture
def mock_bookshelves_model():
    with (
        patch("openlibrary.core.models.Bookshelves.get_users_read_status_of_work") as read_status_mock,
        patch("openlibrary.core.models.Bookshelves.add") as add_mock,
        patch("openlibrary.core.models.Bookshelves.remove") as remove_mock,
        patch("openlibrary.core.bookshelves_events.BookshelvesEvents.delete_by_username_and_work") as delete_events_mock,
    ):
        read_status_mock.return_value = None
        yield read_status_mock, add_mock, remove_mock, delete_events_mock


class TestWorkBookshelvesGet:
    def test_get_work_bookshelves_returns_summary(self, fastapi_client):
        counts = {
            "want_to_read": 2,
            "currently_reading": 3,
            "already_read": 5,
            "stopped_reading": 1,
        }

        with patch("openlibrary.core.models.Bookshelves.get_work_summary", return_value=counts) as summary_mock:
            response = fastapi_client.get("/works/OL123W/bookshelves.json")

        assert response.status_code == 200
        assert response.json() == {"counts": counts}
        summary_mock.assert_called_once_with("123")


class TestWorkBookshelvesPost:
    def test_post_adds_work_to_bookshelf(self, fastapi_client, mock_authenticated_user, mock_bookshelves_model):
        read_status_mock, add_mock, remove_mock, delete_events_mock = mock_bookshelves_model
        add_mock.return_value = 1

        response = fastapi_client.post(
            "/works/OL123W/bookshelves.json",
            data={"bookshelf_id": "1", "edition_id": "/books/OL42M"},
        )

        assert response.status_code == 200
        assert response.json() == {"bookshelves_affected": 1}
        read_status_mock.assert_called_once_with("testuser", "123")
        add_mock.assert_called_once_with(username="testuser", bookshelf_id="1", work_id="123", edition_id=42)
        remove_mock.assert_not_called()
        delete_events_mock.assert_not_called()

    def test_post_accepts_edition_olid_without_path_prefix(self, fastapi_client, mock_authenticated_user, mock_bookshelves_model):
        _, add_mock, _, _ = mock_bookshelves_model
        add_mock.return_value = 1

        response = fastapi_client.post(
            "/works/OL123W/bookshelves.json",
            data={"bookshelf_id": "2", "edition_id": "OL42M"},
        )

        assert response.status_code == 200
        assert response.json() == {"bookshelves_affected": 1}
        add_mock.assert_called_once_with(username="testuser", bookshelf_id="2", work_id="123", edition_id=42)

    def test_post_removes_work_from_bookshelf(self, fastapi_client, mock_authenticated_user, mock_bookshelves_model):
        read_status_mock, add_mock, remove_mock, delete_events_mock = mock_bookshelves_model
        read_status_mock.return_value = 2
        remove_mock.return_value = 1

        response = fastapi_client.post("/works/OL123W/bookshelves.json", data={"bookshelf_id": "-1"})

        assert response.status_code == 200
        assert response.json() == {"bookshelves_affected": 1}
        remove_mock.assert_called_once_with(username="testuser", work_id="123", bookshelf_id="2")
        delete_events_mock.assert_called_once_with("testuser", "123")
        add_mock.assert_not_called()

    def test_post_toggles_current_bookshelf_off(self, fastapi_client, mock_authenticated_user, mock_bookshelves_model):
        read_status_mock, add_mock, remove_mock, delete_events_mock = mock_bookshelves_model
        read_status_mock.return_value = 2
        remove_mock.return_value = 1

        response = fastapi_client.post("/works/OL123W/bookshelves.json", data={"bookshelf_id": "2"})

        assert response.status_code == 200
        assert response.json() == {"bookshelves_affected": 1}
        remove_mock.assert_called_once_with(username="testuser", work_id="123", bookshelf_id="2")
        delete_events_mock.assert_called_once_with("testuser", "123")
        add_mock.assert_not_called()

    def test_dont_remove_prevents_toggle_removal(self, fastapi_client, mock_authenticated_user, mock_bookshelves_model):
        read_status_mock, add_mock, remove_mock, delete_events_mock = mock_bookshelves_model
        read_status_mock.return_value = 2
        add_mock.return_value = 1

        response = fastapi_client.post("/works/OL123W/bookshelves.json", data={"bookshelf_id": "2", "dont_remove": "true"})

        assert response.status_code == 200
        assert response.json() == {"bookshelves_affected": 1}
        add_mock.assert_called_once_with(username="testuser", bookshelf_id="2", work_id="123", edition_id=None)
        remove_mock.assert_not_called()
        delete_events_mock.assert_not_called()

    @pytest.mark.parametrize("data", [{"bookshelf_id": "5"}, {}])
    def test_invalid_or_missing_bookshelf_returns_error(self, fastapi_client, mock_authenticated_user, mock_bookshelves_model, data):
        _, add_mock, remove_mock, delete_events_mock = mock_bookshelves_model

        response = fastapi_client.post("/works/OL123W/bookshelves.json", data=data)

        assert response.status_code == 200
        assert response.json() == {"error": "Invalid bookshelf"}
        add_mock.assert_not_called()
        remove_mock.assert_not_called()
        delete_events_mock.assert_not_called()

    def test_post_requires_authentication(self, fastapi_client):
        response = fastapi_client.post("/works/OL123W/bookshelves.json", data={"bookshelf_id": "1"})

        assert response.status_code == 401

    @pytest.mark.parametrize("path", ["/works/OLnot-a-numberW/bookshelves.json", "/works/OL0W/bookshelves.json"])
    def test_post_rejects_invalid_work_id(self, fastapi_client, mock_authenticated_user, path):
        response = fastapi_client.post(path, data={"bookshelf_id": "1"})

        assert response.status_code == 422

    @pytest.mark.parametrize("edition_id", ["bad", "/works/OL42W", "/books/not-a-number"])
    def test_post_rejects_malformed_edition_id(self, fastapi_client, mock_authenticated_user, edition_id):
        response = fastapi_client.post("/works/OL123W/bookshelves.json", data={"bookshelf_id": "1", "edition_id": edition_id})

        assert response.status_code == 422


class TestWorkBookshelvesLegacyParity:
    def test_add_response_matches_legacy(self, fastapi_client, mock_authenticated_user, mock_bookshelves_model):
        _, add_mock, _, _ = mock_bookshelves_model
        add_mock.return_value = 1
        data = {"bookshelf_id": "1", "edition_id": "/books/OL42M"}

        legacy_response = legacy_bookshelves_json(data)
        fastapi_response = fastapi_client.post("/works/OL123W/bookshelves.json", data=data)

        assert fastapi_response.status_code == 200
        assert fastapi_response.json() == legacy_response

    def test_remove_response_matches_legacy(self, fastapi_client, mock_authenticated_user, mock_bookshelves_model):
        read_status_mock, _, remove_mock, _ = mock_bookshelves_model
        read_status_mock.return_value = 2
        remove_mock.return_value = 1
        data = {"bookshelf_id": "-1"}

        legacy_response = legacy_bookshelves_json(data)
        fastapi_response = fastapi_client.post("/works/OL123W/bookshelves.json", data=data)

        assert fastapi_response.status_code == 200
        assert fastapi_response.json() == legacy_response

    def test_invalid_bookshelf_response_matches_legacy(self, fastapi_client, mock_authenticated_user, mock_bookshelves_model):
        data = {"bookshelf_id": "99"}

        legacy_response = legacy_bookshelves_json(data)
        fastapi_response = fastapi_client.post("/works/OL123W/bookshelves.json", data=data)

        assert fastapi_response.status_code == 200
        assert fastapi_response.json() == legacy_response

    def test_dont_remove_response_matches_legacy(self, fastapi_client, mock_authenticated_user, mock_bookshelves_model):
        read_status_mock, add_mock, _, _ = mock_bookshelves_model
        read_status_mock.return_value = 2
        add_mock.return_value = 1
        data = {"bookshelf_id": "2", "dont_remove": "true"}

        legacy_response = legacy_bookshelves_json(data)
        fastapi_response = fastapi_client.post("/works/OL123W/bookshelves.json", data=data)

        assert fastapi_response.status_code == 200
        assert fastapi_response.json() == legacy_response
