"""Tests for the batch read on openlibrary.core.bookshelves_events."""

from unittest.mock import MagicMock, patch

import web

from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents


def test_get_latest_event_dates_keys_one_row_per_work():
    rows = [
        web.storage(id=5, work_id=1, event_date="2026-08-22"),
        web.storage(id=9, work_id=3, event_date="2025"),
    ]
    oldb = MagicMock()
    oldb.query.return_value = rows
    with patch("openlibrary.core.bookshelves_events.db.get_db", return_value=oldb):
        result = BookshelvesEvents.get_latest_event_dates("tester", [1, 2, 3], BookshelfEvent.FINISH)

    assert result == {
        1: {"id": 5, "event_date": "2026-08-22"},
        3: {"id": 9, "event_date": "2025"},
    }
    query, kwargs = oldb.query.call_args.args[0], oldb.query.call_args.kwargs
    # One row per work, the latest date first within each.
    assert "DISTINCT ON (work_id)" in query
    assert "ORDER BY work_id, event_date DESC" in query
    assert kwargs["vars"] == {"username": "tester", "work_ids": [1, 2, 3], "event_type": BookshelfEvent.FINISH}


def test_get_latest_event_dates_skips_the_db_for_no_works():
    with patch("openlibrary.core.bookshelves_events.db.get_db") as get_db:
        assert BookshelvesEvents.get_latest_event_dates("tester", [], BookshelfEvent.FINISH) == {}
    get_db.assert_not_called()
