"""Tests for the batch read on openlibrary.core.bookshelves_events."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

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


def test_update_event_data_is_callable_on_the_class():
    """update_event_data was missing @classmethod, so calling it on the class
    raised TypeError: missing 1 required positional argument: 'data' (#14200)."""
    oldb = MagicMock()
    with patch("openlibrary.core.bookshelves_events.db.get_db", return_value=oldb):
        BookshelvesEvents.update_event_data(7, '{"note": "test"}')

    oldb.update.assert_called_once_with(
        BookshelvesEvents.TABLENAME,
        where="id=$id",
        vars={"id": 7},
        updated=ANY,
        data='{"note": "test"}',
    )


def test_yearly_read_counts_count_distinct_works():
    """The yearly stats count each work once per year, like the yearly reading goal
    (count_distinct_work_ids_by_user_type_and_year), instead of every finish event."""
    oldb = MagicMock()
    oldb.query.return_value = [MagicMock(year="2026", count=3), MagicMock(year="2025", count=1)]
    with patch("openlibrary.core.bookshelves_events.db.get_db", return_value=oldb):
        result = BookshelvesEvents.get_user_yearly_read_counts("tester")

    assert result == [(2026, 3), (2025, 1)]
    query = oldb.query.call_args.args[0]
    assert "count(DISTINCT work_id)" in query
    assert "count(*)" not in query
    assert oldb.query.call_args.kwargs["vars"] == {"username": "tester", "event_type": BookshelfEvent.FINISH}
