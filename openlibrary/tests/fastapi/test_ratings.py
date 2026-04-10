"""Tests for the FastAPI ratings endpoints."""

from unittest.mock import patch

import pytest


@pytest.fixture
def mock_ratings_model():
    """Prevent real DB calls for Ratings methods."""
    with (
        patch("openlibrary.fastapi.internal.api.models.Ratings.add", autospec=True) as add_mock,
        patch("openlibrary.fastapi.internal.api.models.Ratings.remove", autospec=True) as remove_mock,
    ):
        yield add_mock, remove_mock


class TestRatingsEndpoints:
    def test_get_ratings_returns_legacy_summary(self, fastapi_client):
        expected = {
            "summary": {
                "average": 4.5,
                "count": 2,
                "sortable": 4.2,
            },
            "counts": {
                "1": 0,
                "2": 0,
                "3": 0,
                "4": 1,
                "5": 1,
            },
        }

        with patch("openlibrary.fastapi.internal.api.legacy_ratings.get_ratings_summary", return_value=expected) as mock_summary:
            response = fastapi_client.get("/works/OL123W/ratings.json")

        assert response.status_code == 200
        assert response.json() == expected
        mock_summary.assert_called_once_with(123)

    def test_get_ratings_does_not_inject_sortable_for_empty_summary(self, fastapi_client):
        expected = {
            "summary": {
                "average": None,
                "count": 0,
            },
            "counts": {
                "1": 0,
                "2": 0,
                "3": 0,
                "4": 0,
                "5": 0,
            },
        }

        with patch("openlibrary.fastapi.internal.api.legacy_ratings.get_ratings_summary", return_value=expected):
            response = fastapi_client.get("/works/OL123W/ratings.json")

        assert response.status_code == 200
        assert response.json() == expected

    def test_post_ratings_adds_rating(self, fastapi_client, mock_authenticated_user, mock_ratings_model):
        add_mock, remove_mock = mock_ratings_model
        response = fastapi_client.post(
            "/works/OL123W/ratings.json",
            data={"rating": "5", "edition_id": "/books/OL42M"},
        )

        assert response.status_code == 200
        assert response.json() == {"success": "rating added"}
        add_mock.assert_called_once_with(
            username="testuser",
            work_id=123,
            rating=5,
            edition_id=42,
        )
        remove_mock.assert_not_called()

    def test_post_ratings_removes_rating_when_rating_is_missing(self, fastapi_client, mock_authenticated_user, mock_ratings_model):
        add_mock, remove_mock = mock_ratings_model
        response = fastapi_client.post("/works/OL123W/ratings.json", data={})

        assert response.status_code == 200
        assert response.json() == {"success": "removed rating"}
        remove_mock.assert_called_once_with("testuser", 123)
        add_mock.assert_not_called()

    def test_post_ratings_requires_authentication(self, fastapi_client):
        response = fastapi_client.post("/works/OL123W/ratings.json", data={"rating": "4"})

        assert response.status_code == 401

    @pytest.mark.parametrize("invalid_rating", [0, 6, 10, -1, "abc"])
    def test_post_ratings_invalid_rating_returns_422(self, fastapi_client, mock_authenticated_user, invalid_rating):
        response = fastapi_client.post("/works/OL123W/ratings.json", data={"rating": invalid_rating})

        assert response.status_code == 422
