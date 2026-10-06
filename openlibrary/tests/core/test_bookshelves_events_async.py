"""Tests for the async BookshelvesEvents queries."""

from unittest.mock import patch

import pytest

from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents
from openlibrary.tests.core.async_db_fakes import FakeConnection, FakeConnectionContext


@pytest.mark.asyncio
async def test_count_distinct_work_ids_by_user_type_and_year():
    conn = FakeConnection(rows=[{"count": 3}])
    with patch(
        "openlibrary.core.bookshelves_events.connection",
        return_value=FakeConnectionContext(conn),
    ):
        count = await BookshelvesEvents.count_distinct_work_ids_by_user_type_and_year("testuser", BookshelfEvent.FINISH, 2026)

    assert count == 3
    ((query, params),) = conn.executions
    assert "count(DISTINCT work_id)" in query
    assert "event_date LIKE %(event_date)s" in query
    assert params == {
        "username": "testuser",
        "event_type": BookshelfEvent.FINISH,
        "event_date": "2026%",
    }
