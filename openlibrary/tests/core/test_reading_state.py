"""Tests for openlibrary.core.reading_state — one round of queries for a batch of works."""

from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core.bookshelves_events import BookshelfEvent
from openlibrary.core.reading_state import get_reading_state


@pytest.mark.asyncio
async def test_every_requested_work_is_present_with_nulls_where_there_is_no_state():
    shelves = [{"work_id": 1, "bookshelf_id": 3}]
    ratings = {1: 4, 3: 2}
    finishes = {1: {"id": 77, "event_date": "2026-08"}}
    with (
        patch("openlibrary.core.reading_state.Bookshelves.get_users_read_status_of_works", new_callable=AsyncMock, return_value=shelves) as shelves_mock,
        patch("openlibrary.core.reading_state.Ratings.get_users_ratings_of_works", new_callable=AsyncMock, return_value=ratings) as ratings_mock,
        patch("openlibrary.core.reading_state.BookshelvesEvents.get_latest_event_dates", new_callable=AsyncMock, return_value=finishes) as finishes_mock,
    ):
        result = await get_reading_state("tester", [1, 2, 3])

    assert result == {
        1: {"shelf": 3, "rating": 4, "read_date": "2026-08", "event_id": 77},
        2: {"shelf": None, "rating": None, "read_date": None, "event_id": None},
        3: {"shelf": None, "rating": 2, "read_date": None, "event_id": None},
    }
    shelves_mock.assert_awaited_once_with("tester", [1, 2, 3])
    ratings_mock.assert_awaited_once_with("tester", [1, 2, 3])
    finishes_mock.assert_awaited_once_with("tester", [1, 2, 3], BookshelfEvent.FINISH)


@pytest.mark.asyncio
async def test_no_works_means_no_queries():
    with (
        patch("openlibrary.core.reading_state.Bookshelves.get_users_read_status_of_works", new_callable=AsyncMock) as shelves_mock,
        patch("openlibrary.core.reading_state.Ratings.get_users_ratings_of_works", new_callable=AsyncMock) as ratings_mock,
        patch("openlibrary.core.reading_state.BookshelvesEvents.get_latest_event_dates", new_callable=AsyncMock) as finishes_mock,
    ):
        assert await get_reading_state("tester", []) == {}
    shelves_mock.assert_not_awaited()
    ratings_mock.assert_not_awaited()
    finishes_mock.assert_not_awaited()
