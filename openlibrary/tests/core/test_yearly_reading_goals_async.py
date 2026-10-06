"""Tests for the async yearly reading goals model methods."""

from datetime import datetime
from unittest.mock import patch

import pytest

from openlibrary.core.yearly_reading_goals import YearlyReadingGoal, YearlyReadingGoals
from openlibrary.tests.core.async_db_fakes import FakeConnection, FakeConnectionContext
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

# Column order of the model's SELECT ... FROM yearly_reading_goals queries,
# for class_row to map row values onto YearlyReadingGoal fields.
YEARLY_READING_GOAL_COLUMNS = ("username", "year", "target", "created", "updated")


@pytest.fixture
def fake_connection():
    conn = FakeConnection(columns=YEARLY_READING_GOAL_COLUMNS)
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
