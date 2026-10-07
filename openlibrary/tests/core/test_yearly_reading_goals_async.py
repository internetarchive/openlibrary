"""Unit and integration tests for the async yearly reading goals model.

Unit tests patch the ``async_db`` helpers and check query text and params.
Integration tests (``TestYearlyReadingGoalsIntegration``) run the same
methods against real postgres. See ``docs/core/README.md`` for the pattern.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core import async_db
from openlibrary.core.yearly_reading_goals import YearlyReadingGoal, YearlyReadingGoals
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO


@pytest.fixture
def helpers():
    with (
        patch("openlibrary.core.yearly_reading_goals.fetch_all", new_callable=AsyncMock) as fetch_all,
        patch("openlibrary.core.yearly_reading_goals.fetch_one", new_callable=AsyncMock) as fetch_one,
        patch("openlibrary.core.yearly_reading_goals.execute", new_callable=AsyncMock) as execute,
    ):
        yield SimpleNamespace(fetch_all=fetch_all, fetch_one=fetch_one, execute=execute)


# --- Unit tests (no postgres required) ------------------------------------------


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


# --- Integration tests (real postgres, marked `integration`) -------------------


@pytest.mark.integration
class TestYearlyReadingGoalsIntegration:
    @pytest.mark.asyncio
    async def test_create_and_select_by_username(self, pg_db):
        await YearlyReadingGoals.create("alice", 2026, 25)
        await YearlyReadingGoals.create("alice", 2025, 12)
        await YearlyReadingGoals.create("bob", 2026, 30)

        rows = await YearlyReadingGoals.select_by_username("alice")
        assert len(rows) == 2
        assert {r.year for r in rows} == {2025, 2026}
        assert all(isinstance(r, YearlyReadingGoal) for r in rows)
        assert [r.year for r in rows] == [2025, 2026]

    @pytest.mark.asyncio
    async def test_select_by_username_and_year_returns_one_row(self, pg_db):
        await YearlyReadingGoals.create("alice", 2026, 25)
        await YearlyReadingGoals.create("alice", 2025, 12)
        await YearlyReadingGoals.create("bob", 2026, 30)

        row = await YearlyReadingGoals.select_by_username_and_year("alice", 2026)
        assert isinstance(row, YearlyReadingGoal)
        assert row.username == "alice"
        assert row.year == 2026
        assert row.target == 25

    @pytest.mark.asyncio
    async def test_select_by_username_and_year_returns_none_when_missing(self, pg_db):
        row = await YearlyReadingGoals.select_by_username_and_year("nobody", 2026)
        assert row is None

    @pytest.mark.asyncio
    async def test_select_rejects_unknown_order(self, pg_db):
        with pytest.raises(ValueError, match="Invalid order"):
            await YearlyReadingGoals.select_by_username("alice", order="target ASC; --")

    @pytest.mark.asyncio
    async def test_update_target(self, pg_db):
        await YearlyReadingGoals.create("alice", 2026, 25)

        await YearlyReadingGoals.update_target("alice", 2026, 50)

        row = await YearlyReadingGoals.select_by_username_and_year("alice", 2026)
        assert row is not None
        assert row.target == 50
        assert row.updated is not None

    @pytest.mark.asyncio
    async def test_delete_by_username_and_year(self, pg_db):
        await YearlyReadingGoals.create("alice", 2026, 25)
        await YearlyReadingGoals.create("alice", 2025, 12)

        await YearlyReadingGoals.delete_by_username_and_year("alice", 2026)

        rows = await YearlyReadingGoals.select_by_username("alice")
        assert len(rows) == 1
        assert rows[0].year == 2025

    @pytest.mark.asyncio
    async def test_summary_counts_across_windows(self, pg_db):
        now = datetime.now()
        async with async_db.connection() as conn:
            # updated defaults to now, so set it explicitly. NULL counts for total only.
            await conn.execute("INSERT INTO yearly_reading_goals (username, year, target, updated) VALUES ('a', 2026, 1, NULL)")
            # 3 days ago counts for total, month, week.
            await conn.execute(
                "INSERT INTO yearly_reading_goals (username, year, target, updated) VALUES ('b', 2026, 2, %(d)s)",
                {"d": now - timedelta(days=3)},
            )
            # 10 days ago counts for total and month.
            await conn.execute(
                "INSERT INTO yearly_reading_goals (username, year, target, updated) VALUES ('c', 2026, 3, %(d)s)",
                {"d": now - timedelta(days=10)},
            )

        summary = await YearlyReadingGoals.summary()
        counts = summary["total_yearly_reading_goals"]
        assert counts["total"] == 3
        assert counts["month"] == 2
        assert counts["week"] == 1
