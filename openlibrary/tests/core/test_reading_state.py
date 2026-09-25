"""Tests for openlibrary.core.reading_state — one round of queries for a batch of works."""

from unittest.mock import patch

import web

from openlibrary.core.bookshelves_events import BookshelfEvent
from openlibrary.core.reading_state import get_reading_state


def test_every_requested_work_is_present_with_nulls_where_there_is_no_state():
    shelves = [web.storage(work_id=1, bookshelf_id=3)]
    ratings = {1: 4, 3: 2}
    finishes = {1: {"id": 77, "event_date": "2026-08"}}
    with (
        patch("openlibrary.core.reading_state.Bookshelves.get_users_read_status_of_works", return_value=shelves) as shelves_mock,
        patch("openlibrary.core.reading_state.Ratings.get_users_ratings_of_works", return_value=ratings) as ratings_mock,
        patch("openlibrary.core.reading_state.BookshelvesEvents.get_latest_event_dates", return_value=finishes) as finishes_mock,
    ):
        result = get_reading_state("tester", [1, 2, 3])

    assert result == {
        1: {"shelf": 3, "rating": 4, "read_date": "2026-08", "event_id": 77},
        2: {"shelf": None, "rating": None, "read_date": None, "event_id": None},
        3: {"shelf": None, "rating": 2, "read_date": None, "event_id": None},
    }
    shelves_mock.assert_called_once_with("tester", [1, 2, 3])
    ratings_mock.assert_called_once_with("tester", [1, 2, 3])
    finishes_mock.assert_called_once_with("tester", [1, 2, 3], BookshelfEvent.FINISH)


def test_no_works_means_no_queries():
    with (
        patch("openlibrary.core.reading_state.Bookshelves.get_users_read_status_of_works") as shelves_mock,
        patch("openlibrary.core.reading_state.Ratings.get_users_ratings_of_works") as ratings_mock,
        patch("openlibrary.core.reading_state.BookshelvesEvents.get_latest_event_dates") as finishes_mock,
    ):
        assert get_reading_state("tester", []) == {}
    shelves_mock.assert_not_called()
    ratings_mock.assert_not_called()
    finishes_mock.assert_not_called()
