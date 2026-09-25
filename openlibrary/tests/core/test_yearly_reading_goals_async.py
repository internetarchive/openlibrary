"""Tests for the async yearly reading goals model methods."""

from datetime import datetime
from unittest.mock import patch

import pytest

from openlibrary.core.yearly_reading_goals import YearlyReadingGoals


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows=None):
        self.cursor = FakeCursor(rows)
        self.executions = []
        self.committed = False

    async def execute(self, query, params=None):
        self.executions.append((query, params))
        return self.cursor

    async def commit(self):
        self.committed = True


class FakeConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
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
async def test_select_by_username_async(fake_connection):
    fake_connection.cursor.rows = [{"username": "testuser", "year": 2026, "target": 25}]

    rows = await YearlyReadingGoals.select_by_username_async("testuser")

    assert rows == [{"username": "testuser", "year": 2026, "target": 25}]
    ((query, params),) = fake_connection.executions
    assert "username = %(username)s" in query
    assert params == {"username": "testuser"}


@pytest.mark.asyncio
async def test_select_by_username_async_invalid_order(fake_connection):
    with pytest.raises(ValueError, match="Invalid order"):
        await YearlyReadingGoals.select_by_username_async("testuser", order="target ASC")


@pytest.mark.asyncio
async def test_select_by_username_and_year_async(fake_connection):
    rows = await YearlyReadingGoals.select_by_username_and_year_async("testuser", 2026)

    assert rows == []
    ((query, params),) = fake_connection.executions
    assert "year = %(year)s" in query
    assert params == {"username": "testuser", "year": 2026}


@pytest.mark.asyncio
async def test_create_async(fake_connection):
    await YearlyReadingGoals.create_async("testuser", 2026, 25)

    ((query, params),) = fake_connection.executions
    assert "INSERT INTO yearly_reading_goals" in query
    assert params == {"username": "testuser", "year": 2026, "target": 25}
    assert fake_connection.committed


@pytest.mark.asyncio
async def test_update_target_async(fake_connection):
    await YearlyReadingGoals.update_target_async("testuser", 2026, 30)

    ((query, params),) = fake_connection.executions
    assert "UPDATE yearly_reading_goals" in query
    assert params["username"] == "testuser"
    assert params["year"] == 2026
    assert params["target"] == 30
    assert isinstance(params["updated"], datetime)
    assert fake_connection.committed


@pytest.mark.asyncio
async def test_delete_by_username_and_year_async(fake_connection):
    await YearlyReadingGoals.delete_by_username_and_year_async("testuser", 2026)

    ((query, params),) = fake_connection.executions
    assert "DELETE FROM yearly_reading_goals" in query
    assert params == {"username": "testuser", "year": 2026}
    assert fake_connection.committed
