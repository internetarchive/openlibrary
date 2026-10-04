"""Tests for the async yearly reading goals model methods."""

from datetime import datetime
from unittest.mock import patch

import pytest
from psycopg.rows import TUPLES_OK

from openlibrary.core.yearly_reading_goals import YearlyReadingGoal, YearlyReadingGoals
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO


class FakeCursor:
    class _Result:
        status = TUPLES_OK
        nfields = 5

        @staticmethod
        def fname(index):
            return (b"username", b"year", b"target", b"created", b"updated")[index]

    def __init__(self, connection, rows=None, row_factory=None):
        self.connection = connection
        self.rows = rows or []
        self.pgresult = self._Result()
        self._encoding = "utf-8"
        self._row_maker = row_factory(self) if row_factory is not None else None
        self.fetchall_calls = 0
        self.fetchone_calls = 0

    async def fetchall(self):
        self.fetchall_calls += 1
        if self._row_maker is None:
            return self.rows
        return [self._row_maker(row) for row in self.rows]

    async def fetchone(self):
        self.fetchone_calls += 1
        if not self.rows:
            return None
        return self._row_maker(self.rows[0]) if self._row_maker is not None else self.rows[0]

    async def execute(self, query, params=None):
        self.connection.executions.append((query, params))
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, rows=None):
        self.executions = []
        self.committed = False
        self._cursor = FakeCursor(self, rows)

    async def execute(self, query, params=None):
        self.executions.append((query, params))
        return self._cursor

    def cursor(self, **kwargs):
        return FakeCursor(self, self._cursor.rows, kwargs.get("row_factory"))

    async def commit(self):
        self.committed = True


class FakeConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None:
            await self.conn.commit()
        return False


@pytest.fixture
def fake_connection():
    conn = FakeConnection()
    with patch(
        "openlibrary.core.yearly_reading_goals.connection",
        return_value=FakeConnectionContext(conn),
    ):
        yield conn


@pytest.mark.asyncio
async def test_select_by_username(fake_connection):
    fake_connection._cursor.rows = [("testuser", 2026, 25, datetime(2026, 1, 1), datetime(2026, 1, 2))]

    rows = await YearlyReadingGoals.select_by_username("testuser")

    assert rows == [YearlyReadingGoal("testuser", 2026, 25, datetime(2026, 1, 1), datetime(2026, 1, 2))]
    ((query, params),) = fake_connection.executions
    assert "username = %(username)s" in query
    assert params == {"username": "testuser"}


@pytest.mark.asyncio
async def test_select_by_username_invalid_order(fake_connection):
    with pytest.raises(ValueError, match="Invalid order"):
        await YearlyReadingGoals.select_by_username("testuser", order="target ASC")


@pytest.mark.asyncio
async def test_select_by_username_and_year(fake_connection):
    rows = await YearlyReadingGoals.select_by_username_and_year("testuser", 2026)

    assert rows == []
    ((query, params),) = fake_connection.executions
    assert "year = %(year)s" in query
    assert params == {"username": "testuser", "year": 2026}


@pytest.mark.asyncio
async def test_create(fake_connection):
    await YearlyReadingGoals.create("testuser", 2026, 25)

    ((query, params),) = fake_connection.executions
    assert "INSERT INTO yearly_reading_goals" in query
    assert params == {"username": "testuser", "year": 2026, "target": 25}
    assert fake_connection.committed


@pytest.mark.asyncio
async def test_update_target(fake_connection):
    await YearlyReadingGoals.update_target("testuser", 2026, 30)

    ((query, params),) = fake_connection.executions
    assert "UPDATE yearly_reading_goals" in query
    assert params["username"] == "testuser"
    assert params["year"] == 2026
    assert params["target"] == 30
    assert isinstance(params["updated"], datetime)
    assert fake_connection.committed


@pytest.mark.asyncio
async def test_delete_by_username_and_year(fake_connection):
    await YearlyReadingGoals.delete_by_username_and_year("testuser", 2026)

    ((query, params),) = fake_connection.executions
    assert "DELETE FROM yearly_reading_goals" in query
    assert params == {"username": "testuser", "year": 2026}
    assert fake_connection.committed


@pytest.mark.asyncio
async def test_summary_counts_every_window_in_one_query(fake_connection):
    fake_connection._cursor.rows = [{"total": 10, "month": 4, "week": 2}]

    summary = await YearlyReadingGoals.summary()

    assert summary == {"total_yearly_reading_goals": {"total": 10, "month": 4, "week": 2}}
    ((query, params),) = fake_connection.executions
    assert "count(*) FILTER (WHERE updated >= %(month_ago)s)" in query
    assert "count(*) FILTER (WHERE updated >= %(week_ago)s)" in query
    assert params == {"month_ago": DATE_ONE_MONTH_AGO, "week_ago": DATE_ONE_WEEK_AGO}
    assert fake_connection._cursor.fetchone_calls == 1
    assert fake_connection._cursor.fetchall_calls == 0
