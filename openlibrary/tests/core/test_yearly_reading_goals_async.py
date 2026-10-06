"""Tests for the async yearly reading goals model methods.

The model's queries go through the async_db single-statement helpers;
the ``helpers`` fixture patches them, so each test sets a plain return
value and asserts the query and params the method passes. Row mapping
through class_row is covered in test_async_db_helpers, so the SELECT
column order is pinned here by asserting the query text itself.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core.yearly_reading_goals import YearlyReadingGoal, YearlyReadingGoals
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO


@pytest.fixture
def helpers():
    """Patch the async_db helpers this model imports.

    Tests set ``return_value`` on the helper their method uses and assert
    its call through ``await_args``.
    """
    with (
        patch("openlibrary.core.yearly_reading_goals.fetch_all", new_callable=AsyncMock) as fetch_all,
        patch("openlibrary.core.yearly_reading_goals.fetch_one", new_callable=AsyncMock) as fetch_one,
        patch("openlibrary.core.yearly_reading_goals.execute", new_callable=AsyncMock) as execute,
    ):
        yield SimpleNamespace(fetch_all=fetch_all, fetch_one=fetch_one, execute=execute)


@pytest.mark.asyncio
async def test_select_by_username(helpers):
    goal = YearlyReadingGoal("testuser", 2026, 25, datetime(2026, 1, 1), datetime(2026, 1, 2))
    helpers.fetch_all.return_value = [goal]

    rows = await YearlyReadingGoals.select_by_username("testuser")

    assert rows == [goal]
    (query, params), _kwargs = helpers.fetch_all.await_args
    assert query.startswith("SELECT username, year, target, created, updated FROM yearly_reading_goals")
    assert "username = %(username)s" in query
    assert query.endswith("ORDER BY year ASC")
    assert params == {"username": "testuser"}


@pytest.mark.asyncio
async def test_select_by_username_invalid_order(helpers):
    with pytest.raises(ValueError, match="Invalid order"):
        await YearlyReadingGoals.select_by_username("testuser", order="target ASC")

    helpers.fetch_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_select_by_username_and_year(helpers):
    goal = YearlyReadingGoal("testuser", 2026, 25, None, None)
    helpers.fetch_one.return_value = goal

    row = await YearlyReadingGoals.select_by_username_and_year("testuser", 2026)

    assert row is goal
    (query, params), _kwargs = helpers.fetch_one.await_args
    assert query.startswith("SELECT username, year, target, created, updated FROM yearly_reading_goals")
    assert "username = %(username)s" in query
    assert "year = %(year)s" in query
    assert params == {"username": "testuser", "year": 2026}


@pytest.mark.asyncio
async def test_select_by_username_and_year_without_goal(helpers):
    helpers.fetch_one.return_value = None

    assert await YearlyReadingGoals.select_by_username_and_year("testuser", 2026) is None


@pytest.mark.asyncio
async def test_create(helpers):
    await YearlyReadingGoals.create("testuser", 2026, 25)

    (query, params), _kwargs = helpers.execute.await_args
    assert query == "INSERT INTO yearly_reading_goals (username, year, target) VALUES (%(username)s, %(year)s, %(target)s)"
    assert params == {"username": "testuser", "year": 2026, "target": 25}


@pytest.mark.asyncio
async def test_update_target(helpers):
    await YearlyReadingGoals.update_target("testuser", 2026, 30)

    (query, params), _kwargs = helpers.execute.await_args
    assert query.startswith("UPDATE yearly_reading_goals SET target = %(target)s")
    assert params["username"] == "testuser"
    assert params["year"] == 2026
    assert params["target"] == 30
    assert isinstance(params["updated"], datetime)


@pytest.mark.asyncio
async def test_delete_by_username_and_year(helpers):
    await YearlyReadingGoals.delete_by_username_and_year("testuser", 2026)

    (query, params), _kwargs = helpers.execute.await_args
    assert query == "DELETE FROM yearly_reading_goals WHERE username = %(username)s AND year = %(year)s"
    assert params == {"username": "testuser", "year": 2026}


@pytest.mark.asyncio
async def test_summary_counts_every_window_in_one_query(helpers):
    helpers.fetch_one.return_value = {"total": 10, "month": 4, "week": 2}

    summary = await YearlyReadingGoals.summary()

    assert summary == {"total_yearly_reading_goals": {"total": 10, "month": 4, "week": 2}}
    (query, params), _kwargs = helpers.fetch_one.await_args
    assert "count(*) FILTER (WHERE updated >= %(month_ago)s)" in query
    assert "count(*) FILTER (WHERE updated >= %(week_ago)s)" in query
    assert params == {"month_ago": DATE_ONE_MONTH_AGO, "week_ago": DATE_ONE_WEEK_AGO}
