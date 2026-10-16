"""Unit and integration tests for the async booknotes model."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core import async_db
from openlibrary.core.booknotes import Booknote, Booknotes
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO


@pytest.fixture
def helpers():
    with (
        patch("openlibrary.core.booknotes.fetch_all", new_callable=AsyncMock) as fetch_all,
        patch("openlibrary.core.booknotes.fetch_one", new_callable=AsyncMock) as fetch_one,
        patch("openlibrary.core.booknotes.fetch_val", new_callable=AsyncMock) as fetch_val,
        patch("openlibrary.core.booknotes.execute", new_callable=AsyncMock) as execute,
    ):
        yield SimpleNamespace(fetch_all=fetch_all, fetch_one=fetch_one, fetch_val=fetch_val, execute=execute)


@pytest.mark.asyncio
async def test_summary(helpers):
    helpers.fetch_one.return_value = {
        "total_notes": 10,
        "month_notes": 4,
        "week_notes": 2,
        "total_users": 5,
        "month_users": 3,
        "week_users": 2,
    }

    assert await Booknotes.summary() == {
        "total_notes_created": {"total": 10, "month": 4, "week": 2},
        "total_note_takers": {"total": 5, "month": 3, "week": 2},
    }
    (query, params), _kwargs = helpers.fetch_one.await_args
    assert "FILTER (WHERE created >= %(month_ago)s)" in query
    assert "FILTER (WHERE created >= %(week_ago)s)" in query
    assert params == {"month_ago": DATE_ONE_MONTH_AGO, "week_ago": DATE_ONE_WEEK_AGO}


@pytest.mark.asyncio
async def test_add_uses_upsert_and_returns_booknote(helpers):
    note = Booknote("alice", 1, -1, "hello", datetime.now(), datetime.now())
    helpers.fetch_one.return_value = note

    assert await Booknotes.add("alice", 1, "hello") is note
    (query, params), kwargs = helpers.fetch_one.await_args
    assert "ON CONFLICT (username, work_id, edition_id)" in query
    assert "DO UPDATE SET notes = EXCLUDED.notes" in query
    assert "RETURNING username, work_id, edition_id, notes, created, updated" in query
    assert params == {"username": "alice", "work_id": 1, "edition_id": -1, "notes": "hello"}
    assert kwargs["row_factory"] is not None


@pytest.mark.asyncio
async def test_get_patron_booknotes_builds_filtered_query(helpers):
    note = Booknote("alice", 1, 2, "hello", None, None)
    helpers.fetch_all.return_value = [note]

    assert await Booknotes.get_patron_booknotes("alice", work_id=1, edition_id=2, search="ell", page=2) == [note]
    (query, params), kwargs = helpers.fetch_all.await_args
    assert "work_id = %(work_id)s AND edition_id = %(edition_id)s" in query
    assert "notes LIKE %(search_pattern)s" in query
    assert params == {
        "username": "alice",
        "work_id": 1,
        "edition_id": 2,
        "limit": 100,
        "offset": 100,
        "search_pattern": "%ell%",
    }
    assert kwargs["row_factory"] is not None


@pytest.mark.asyncio
async def test_count_works_with_notes_by_user(helpers):
    helpers.fetch_val.return_value = 3

    assert await Booknotes.count_works_with_notes_by_user("alice") == 3
    (query, params), _kwargs = helpers.fetch_val.await_args
    assert "COUNT(DISTINCT work_id)" in query
    assert params == {"username": "alice"}


@pytest.mark.asyncio
async def test_remove(helpers):
    await Booknotes.remove("alice", 1, edition_id=2)

    (query, params), _kwargs = helpers.execute.await_args
    assert query == "DELETE FROM booknotes WHERE username = %(username)s AND work_id = %(work_id)s AND edition_id = %(edition_id)s"
    assert params == {"username": "alice", "work_id": 1, "edition_id": 2}


@pytest.mark.asyncio
async def test_remove_none_work_id_is_noop(helpers):
    await Booknotes.remove("alice", None)
    helpers.execute.assert_not_awaited()


def test_sync_bridges_call_async_methods():
    def run_coroutine(coro):
        coro.close()
        return 7

    with patch("openlibrary.core.booknotes.async_bridge.run", side_effect=run_coroutine) as run:
        assert Booknotes.count_works_with_notes_by_user_sync("alice") == 7
        run.assert_called_once()


@pytest.mark.integration
class TestBooknotesIntegration:
    @pytest.mark.asyncio
    async def test_add_update_search_counts_and_remove(self, pg_db):
        first = await Booknotes.add("alice", 1, "A useful note")
        assert first.created is not None
        assert first.updated is not None

        updated = await Booknotes.add("alice", 1, "An updated note")
        assert updated.notes == "An updated note"
        assert updated.created == first.created
        assert updated.updated >= first.updated

        await Booknotes.add("alice", 2, "Another useful note", edition_id=10)
        await Booknotes.add("bob", 1, "A note by Bob")
        rows = await Booknotes.get_patron_booknotes("alice", search="useful")
        assert {row.work_id for row in rows} == {2}
        assert await Booknotes.count_works_with_notes_by_user("alice") == 2

        await Booknotes.remove("alice", 1)
        assert await Booknotes.get_patron_booknote("alice", 1) is None
        assert await Booknotes.count_works_with_notes_by_user("alice") == 1

    @pytest.mark.asyncio
    async def test_summary_uses_postgres_filter_aggregates(self, pg_db):
        now = datetime.now()
        async with async_db.connection() as conn:
            await conn.execute(
                "INSERT INTO booknotes (username, work_id, notes, created) VALUES ('old', 1, 'old', %(created)s)", {"created": now - timedelta(days=40)}
            )
            await conn.execute(
                "INSERT INTO booknotes (username, work_id, notes, created) VALUES ('month', 2, 'month', %(created)s)", {"created": now - timedelta(days=10)}
            )
            await conn.execute(
                "INSERT INTO booknotes (username, work_id, notes, created) VALUES ('week', 3, 'week', %(created)s)", {"created": now - timedelta(days=2)}
            )

        summary = await Booknotes.summary()
        assert summary == {
            "total_notes_created": {"total": 3, "month": 2, "week": 1},
            "total_note_takers": {"total": 3, "month": 2, "week": 1},
        }
