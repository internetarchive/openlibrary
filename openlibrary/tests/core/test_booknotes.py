"""Unit and integration tests for the async booknotes model."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
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
    @pytest.mark.parametrize("edition_id", [Booknotes.NULL_EDITION_VALUE, 10])
    async def test_repeated_add_keeps_one_row_with_latest_values(self, pg_db, edition_id):
        before = await async_db.fetch_val("SELECT CURRENT_TIMESTAMP AT TIME ZONE 'UTC'")
        first = await Booknotes.add("alice", 1, "First note", edition_id=edition_id)
        assert isinstance(first, Booknote)
        assert first.created == first.updated
        assert first.updated >= before

        original_time = datetime(2000, 1, 1)
        params = {"username": "alice", "work_id": 1, "edition_id": edition_id, "original_time": original_time}
        await async_db.execute(
            """
            UPDATE booknotes SET created = %(original_time)s, updated = %(original_time)s
            WHERE username = %(username)s AND work_id = %(work_id)s AND edition_id = %(edition_id)s
            """,
            params,
        )

        updated = await Booknotes.add("alice", 1, "Updated 'note' — नया", edition_id=edition_id)

        rows = await Booknotes.get_booknotes_for_work(1)
        assert rows == [updated]
        assert updated.username == "alice"
        assert updated.work_id == 1
        assert updated.edition_id == edition_id
        assert updated.notes == "Updated 'note' — नया"
        assert updated.created == original_time
        assert updated.updated >= before

    @pytest.mark.asyncio
    async def test_add_stamps_utc_timestamps(self, pg_db, monkeypatch):
        # Run the app and the DB session far from UTC so a local-time value would stand out.
        monkeypatch.setenv("TZ", "Pacific/Kiritimati")  # UTC+14
        monkeypatch.setenv("PGTZ", "Pacific/Kiritimati")  # libpq sets the session TimeZone from this
        time.tzset()
        try:
            first = await Booknotes.add("alice", 1, "First note")
            second = await Booknotes.add("alice", 1, "Second note")
        finally:
            monkeypatch.undo()
            time.tzset()

        utc_now = datetime.now(UTC).replace(tzinfo=None)
        assert abs(first.created - utc_now) < timedelta(minutes=5)
        assert abs(second.updated - utc_now) < timedelta(minutes=5)
        assert second.created == first.created
        assert second.updated >= first.updated

    @pytest.mark.asyncio
    async def test_add_leaves_other_users_works_and_editions_untouched(self, pg_db):
        await Booknotes.add("alice", 1, "Original")
        other_notes = [
            await Booknotes.add("bob", 1, "Other user"),
            await Booknotes.add("alice", 2, "Other work"),
            await Booknotes.add("alice", 1, "Other edition", edition_id=10),
        ]

        await Booknotes.add("alice", 1, "Replacement")

        assert await async_db.fetch_val("SELECT count(*) FROM booknotes") == 4
        for note in other_notes:
            assert await Booknotes.get_patron_booknote(note.username, note.work_id, note.edition_id) == note

    @pytest.mark.asyncio
    async def test_concurrent_adds_keep_one_row_and_return_saved_notes(self, pg_db):
        texts = ["First concurrent note", "Second concurrent note"]
        saved = await asyncio.gather(*(Booknotes.add("alice", 1, text) for text in texts))

        assert [note.notes for note in saved] == texts
        rows = await Booknotes.get_booknotes_for_work(1)
        assert len(rows) == 1
        assert rows[0] in saved
        assert all(note.created == rows[0].created for note in saved)

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
