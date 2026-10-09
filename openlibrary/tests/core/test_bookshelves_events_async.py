"""Unit and integration tests for the async BookshelvesEvents queries. See ``docs/core/database.md``."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core import async_db
from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents

# --- Unit test (no postgres required) ------------------------------------------


@pytest.mark.asyncio
async def test_count_distinct_work_ids_by_user_type_and_year():
    with patch(
        "openlibrary.core.bookshelves_events.fetch_val",
        new_callable=AsyncMock,
        return_value=3,
    ) as mock_fetch_val:
        count = await BookshelvesEvents.count_distinct_work_ids_by_user_type_and_year("testuser", BookshelfEvent.FINISH, 2026)

    assert count == 3
    (query, params), _kwargs = mock_fetch_val.await_args
    assert "count(DISTINCT work_id)" in query
    assert "event_date LIKE %(event_date)s" in query
    assert params == {
        "username": "testuser",
        "event_type": BookshelfEvent.FINISH,
        "event_date": "2026%",
    }


@pytest.fixture
def helpers():
    with (
        patch("openlibrary.core.bookshelves_events.fetch_all", new_callable=AsyncMock) as fetch_all,
        patch("openlibrary.core.bookshelves_events.fetch_one", new_callable=AsyncMock) as fetch_one,
    ):
        yield SimpleNamespace(fetch_all=fetch_all, fetch_one=fetch_one)


@pytest.mark.asyncio
async def test_create_event(helpers):
    helpers.fetch_one.return_value = {"id": 123}

    event_id = await BookshelvesEvents.create_event("alice", 42, None, "2026-05-10", event_type=BookshelfEvent.START)

    assert event_id == 123
    (query, params), _kwargs = helpers.fetch_one.await_args
    assert query.startswith("INSERT INTO bookshelves_events")
    assert "RETURNING id" in query
    assert params == {
        "username": "alice",
        "work_id": 42,
        "edition_id": BookshelvesEvents.NULL_EDITION_ID,
        "event_type": BookshelfEvent.START,
        "event_date": "2026-05-10",
    }


@pytest.mark.asyncio
async def test_select_by_id(helpers):
    expected = [{"id": 123, "username": "alice"}]
    helpers.fetch_all.return_value = expected

    rows = await BookshelvesEvents.select_by_id(123)

    assert rows == expected
    (query, params), _kwargs = helpers.fetch_all.await_args
    assert query == "SELECT * FROM bookshelves_events WHERE id = %(id)s"
    assert params == {"id": 123}


@pytest.mark.asyncio
async def test_update_event(helpers):
    helpers.fetch_all.return_value = [{"id": 123}]

    rows_updated = await BookshelvesEvents.update_event(123, edition_id=99, event_date="2026-05-10")

    assert rows_updated == 1
    (query, params), _kwargs = helpers.fetch_all.await_args
    assert query.startswith("UPDATE bookshelves_events SET")
    assert "edition_id = %(edition_id)s" in query
    assert "event_date = %(event_date)s" in query
    assert "updated = %(updated)s" in query
    assert query.endswith("WHERE id = %(id)s RETURNING id")
    assert params["id"] == 123
    assert params["edition_id"] == 99
    assert params["event_date"] == "2026-05-10"
    assert params["updated"] is not None


@pytest.mark.asyncio
async def test_update_event_without_changes_does_not_query(helpers):
    assert await BookshelvesEvents.update_event(123) == 0
    helpers.fetch_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_by_id(helpers):
    helpers.fetch_all.return_value = [{"id": 123}]

    rows_deleted = await BookshelvesEvents.delete_by_id(123)

    assert rows_deleted == 1
    helpers.fetch_all.assert_awaited_once_with("DELETE FROM bookshelves_events WHERE id = %(id)s RETURNING id", {"id": 123})


@pytest.mark.integration
class TestBookshelvesEventsCheckinIntegration:
    @pytest.mark.asyncio
    async def test_create_select_update_delete(self, pg_db):
        event_id = await BookshelvesEvents.create_event("alice", 42, None, "2026-05-10", event_type=BookshelfEvent.START)
        rows = await BookshelvesEvents.select_by_id(event_id)
        assert len(rows) == 1
        assert rows[0]["username"] == "alice"
        assert rows[0]["edition_id"] == BookshelvesEvents.NULL_EDITION_ID

        assert await BookshelvesEvents.update_event(event_id, edition_id=99, event_date="2026-05-11") == 1
        updated = await BookshelvesEvents.select_by_id(event_id)
        assert updated[0]["edition_id"] == 99
        assert updated[0]["event_date"] == "2026-05-11"

        assert await BookshelvesEvents.delete_by_id(event_id) == 1
        assert await BookshelvesEvents.select_by_id(event_id) == []


@pytest.mark.integration
class TestBookshelvesEventsReadingGoalIntegration:
    @pytest.mark.asyncio
    async def test_count_distinct_work_ids_by_user_type_and_year(self, pg_db):
        async with async_db.connection() as conn:
            for work_id in (101, 102, 103):
                await conn.execute(
                    f"INSERT INTO {BookshelvesEvents.TABLENAME} (username, work_id, edition_id, event_type, event_date) "
                    "VALUES (%(u)s, %(w)s, %(e)s, %(t)s, %(d)s)",
                    {"u": "alice", "w": work_id, "e": 1, "t": BookshelfEvent.FINISH, "d": "2026-05-01"},
                )
            # Duplicate on 101 stays distinct. START and 2025 rows must not count.
            await conn.execute(
                f"INSERT INTO {BookshelvesEvents.TABLENAME} (username, work_id, edition_id, event_type, event_date) VALUES (%(u)s, %(w)s, %(e)s, %(t)s, %(d)s)",
                {"u": "alice", "w": 101, "e": 1, "t": BookshelfEvent.FINISH, "d": "2026-06-01"},
            )
            await conn.execute(
                f"INSERT INTO {BookshelvesEvents.TABLENAME} (username, work_id, edition_id, event_type, event_date) VALUES (%(u)s, %(w)s, %(e)s, %(t)s, %(d)s)",
                {"u": "alice", "w": 104, "e": 1, "t": BookshelfEvent.START, "d": "2026-05-01"},
            )
            await conn.execute(
                f"INSERT INTO {BookshelvesEvents.TABLENAME} (username, work_id, edition_id, event_type, event_date) VALUES (%(u)s, %(w)s, %(e)s, %(t)s, %(d)s)",
                {"u": "alice", "w": 105, "e": 1, "t": BookshelfEvent.FINISH, "d": "2025-05-01"},
            )

        count = await BookshelvesEvents.count_distinct_work_ids_by_user_type_and_year("alice", BookshelfEvent.FINISH, 2026)
        assert count == 3

    @pytest.mark.asyncio
    async def test_count_distinct_work_ids_zero_when_no_events(self, pg_db):
        count = await BookshelvesEvents.count_distinct_work_ids_by_user_type_and_year("nobody", BookshelfEvent.FINISH, 2026)
        assert count == 0


@pytest.mark.integration
class TestBookshelvesEventsSyncBridgeIntegration:
    """Integration tests for the synchronous bridge methods (_sync suffix)."""

    @pytest.mark.asyncio
    async def test_create_event_sync(self, pg_db):
        event_id = BookshelvesEvents.create_event_sync("alice", 42, None, "2026-05-10", event_type=BookshelfEvent.START)
        assert isinstance(event_id, int)
        rows = await BookshelvesEvents.select_by_id(event_id)
        assert len(rows) == 1
        assert rows[0]["username"] == "alice"
        assert rows[0]["work_id"] == 42
        assert rows[0]["edition_id"] == BookshelvesEvents.NULL_EDITION_ID

    @pytest.mark.asyncio
    async def test_select_by_id_sync(self, pg_db):
        event_id = await BookshelvesEvents.create_event("alice", 42, None, "2026-05-10", event_type=BookshelfEvent.START)
        rows = BookshelvesEvents.select_by_id_sync(event_id)
        assert len(rows) == 1
        assert rows[0]["id"] == event_id

    @pytest.mark.asyncio
    async def test_update_event_sync(self, pg_db):
        event_id = await BookshelvesEvents.create_event("alice", 42, None, "2026-05-10", event_type=BookshelfEvent.START)
        rows_updated = BookshelvesEvents.update_event_sync(event_id, edition_id=99, event_date="2026-05-11")
        assert rows_updated == 1
        rows = BookshelvesEvents.select_by_id_sync(event_id)
        assert rows[0]["edition_id"] == 99
        assert rows[0]["event_date"] == "2026-05-11"

    @pytest.mark.asyncio
    async def test_update_event_sync_no_changes(self, pg_db):
        event_id = await BookshelvesEvents.create_event("alice", 42, None, "2026-05-10", event_type=BookshelfEvent.START)
        rows_updated = BookshelvesEvents.update_event_sync(event_id)
        assert rows_updated == 0

    @pytest.mark.asyncio
    async def test_delete_by_id_sync(self, pg_db):
        event_id = await BookshelvesEvents.create_event("alice", 42, None, "2026-05-10", event_type=BookshelfEvent.START)
        rows_deleted = BookshelvesEvents.delete_by_id_sync(event_id)
        assert rows_deleted == 1
        rows = BookshelvesEvents.select_by_id_sync(event_id)
        assert rows == []
