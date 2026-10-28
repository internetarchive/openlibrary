"""Tests for the batch read on openlibrary.core.bookshelves_events."""

from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents


@pytest.mark.asyncio
async def test_get_latest_event_dates_keys_one_row_per_work():
    rows = [
        {"id": 5, "work_id": 1, "event_date": "2026-08-22"},
        {"id": 9, "work_id": 3, "event_date": "2025"},
    ]
    with patch("openlibrary.core.bookshelves_events.fetch_all", new_callable=AsyncMock, return_value=rows) as fetch_all:
        result = await BookshelvesEvents.get_latest_event_dates("tester", [1, 2, 3], BookshelfEvent.FINISH)

    assert result == {
        1: {"id": 5, "event_date": "2026-08-22"},
        3: {"id": 9, "event_date": "2025"},
    }
    query, params = fetch_all.await_args.args
    # One row per work, the latest date first within each.
    assert "DISTINCT ON (work_id)" in query
    assert "ORDER BY work_id, event_date DESC" in query
    assert params == {"username": "tester", "work_ids": [1, 2, 3], "event_type": BookshelfEvent.FINISH}


@pytest.mark.asyncio
async def test_get_latest_event_dates_skips_the_db_for_no_works():
    with patch("openlibrary.core.bookshelves_events.fetch_all", new_callable=AsyncMock) as fetch_all:
        assert await BookshelvesEvents.get_latest_event_dates("tester", [], BookshelfEvent.FINISH) == {}
    fetch_all.assert_not_awaited()
