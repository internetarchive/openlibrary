"""Tests for GET /partials/ReadingState.json — the batched opening state for shelf buttons."""

from unittest.mock import patch

URL = "/partials/ReadingState.json"
# Importing the router module here would run the openlibrary plugin setup
# before the app fixture does, so the cap is restated rather than imported.
MAX_READING_STATE_WORKS = 100


class TestReadingStatePartial:
    def test_requires_authentication(self, fastapi_client):
        response = fastapi_client.get(URL, params={"work_ids": "OL1W"})
        assert response.status_code == 401

    def test_returns_every_work_keyed_by_olid(self, fastapi_client, mock_authenticated_user):
        states = {
            1: {"shelf": 2, "rating": None, "read_date": None, "event_id": None},
            2: {"shelf": 3, "rating": 5, "read_date": "2026-08", "event_id": 7},
        }
        with patch("openlibrary.plugins.openlibrary.partials.get_reading_state", return_value=states) as get_state:
            response = fastapi_client.get(URL, params={"work_ids": "OL1W,OL2W"})

        assert response.status_code == 200
        assert response.json() == {
            "user_key": "/people/testuser",
            "works": {
                "OL1W": {"shelf": 2, "rating": None, "read_date": None, "event_id": None},
                "OL2W": {"shelf": 3, "rating": 5, "read_date": "2026-08", "event_id": 7},
            },
        }
        get_state.assert_called_once_with("testuser", [1, 2])

    def test_rejects_anything_that_is_not_a_work_olid(self, fastapi_client, mock_authenticated_user):
        response = fastapi_client.get(URL, params={"work_ids": "OL1W,OL2M"})
        assert response.status_code == 422
        assert "OL2M" in response.text

    def test_caps_the_batch(self, fastapi_client, mock_authenticated_user):
        too_many = ",".join(f"OL{i}W" for i in range(1, MAX_READING_STATE_WORKS + 2))
        response = fastapi_client.get(URL, params={"work_ids": too_many})
        assert response.status_code == 422

    def test_tolerates_blank_entries(self, fastapi_client, mock_authenticated_user):
        with patch("openlibrary.plugins.openlibrary.partials.get_reading_state", return_value={}) as get_state:
            response = fastapi_client.get(URL, params={"work_ids": "OL1W,,"})
        assert response.status_code == 200
        get_state.assert_called_once_with("testuser", [1])
