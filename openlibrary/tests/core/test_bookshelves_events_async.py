"""Tests for the async BookshelvesEvents queries."""

from unittest.mock import patch

import pytest

from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def fetchone(self):
        return self.rows[0]


class FakeConnection:
    def __init__(self, rows=None):
        self.cursor = FakeCursor(rows)
        self.executions = []

    async def execute(self, query, params=None):
        self.executions.append((query, params))
        return self.cursor


class FakeConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


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
