"""Tests for the reading-state endpoint backing the book components."""

from unittest.mock import patch

import web


class TestReadingStateEndpoint:
    def test_requires_login(self, fastapi_client):
        response = fastapi_client.get("/reading-state.json", params={"work_ids": "OL1W"})
        assert response.status_code == 401

    def test_returns_shelves_and_ratings(self, fastapi_client, mock_authenticated_user):
        rows = [web.storage(work_id=1, bookshelf_id=2)]
        with (
            patch("openlibrary.fastapi.reading_state.Bookshelves.get_users_read_status_of_works", return_value=rows) as shelves,
            patch("openlibrary.fastapi.reading_state.Ratings.get_users_ratings_of_works", return_value={2: 5}) as ratings,
        ):
            response = fastapi_client.get("/reading-state.json", params={"work_ids": "OL1W,OL2W"})
        assert response.status_code == 200
        assert response.json() == {"shelves": {"OL1W": 2}, "ratings": {"OL2W": 5}}
        shelves.assert_called_once_with("testuser", [1, 2])
        ratings.assert_called_once_with("testuser", [1, 2])
