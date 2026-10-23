"""Unit and PostgreSQL integration tests for async Bookshelves queries."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core import async_db
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents


@pytest.fixture
def helpers():
    with (
        patch("openlibrary.core.bookshelves.fetch_all", new_callable=AsyncMock) as fetch_all,
        patch("openlibrary.core.bookshelves.fetch_val", new_callable=AsyncMock) as fetch_val,
    ):
        yield SimpleNamespace(fetch_all=fetch_all, fetch_val=fetch_val)


@pytest.fixture
def db_connection():
    lock_cursor = SimpleNamespace(fetchone=AsyncMock(return_value={"pg_advisory_xact_lock": None}))
    status_cursor = SimpleNamespace(fetchone=AsyncMock(return_value=None))
    insert_cursor = SimpleNamespace(rowcount=1)
    conn = SimpleNamespace(execute=AsyncMock(side_effect=[lock_cursor, status_cursor, insert_cursor]))

    @asynccontextmanager
    async def fake_connection():
        yield conn

    with patch("openlibrary.core.bookshelves.connection", return_value=fake_connection()):
        yield conn


@pytest.mark.asyncio
async def test_get_users_read_status_of_work(helpers):
    helpers.fetch_val.return_value = 2

    status = await Bookshelves.get_users_read_status_of_work("alice", "42")

    assert status == 2
    (query, params), _kwargs = helpers.fetch_val.await_args
    assert "bookshelf_id = ANY(%(bookshelf_ids)s)" in query
    assert "username = %(username)s AND work_id = %(work_id)s" in query
    assert params == {"bookshelf_ids": [1, 2, 3, 4], "username": "alice", "work_id": 42}


@pytest.mark.asyncio
async def test_add_inserts_when_work_is_not_shelved(db_connection):

    result = await Bookshelves.add("alice", "2", "42", edition_id=7)

    assert result == 1
    assert db_connection.execute.await_count == 3
    lock_call, status_call, insert_call = db_connection.execute.await_args_list
    assert lock_call.args == (
        "SELECT pg_advisory_xact_lock(hashtext(%(username)s), %(work_id)s)",
        {"username": "alice", "work_id": 42},
    )
    assert status_call.args[0].startswith("SELECT bookshelf_id FROM bookshelves_books")
    assert "bookshelf_id = ANY(%(bookshelf_ids)s)" in status_call.args[0]
    assert "ON CONFLICT (username, work_id, bookshelf_id) DO UPDATE" in insert_call.args[0]
    assert insert_call.args[1] == {"work_id": 42, "username": "alice", "bookshelf_id": 2, "edition_id": 7}


@pytest.mark.asyncio
async def test_add_updates_existing_shelf(db_connection):
    db_connection.execute.side_effect = [
        SimpleNamespace(fetchone=AsyncMock(return_value={"pg_advisory_xact_lock": None})),
        SimpleNamespace(fetchone=AsyncMock(return_value={"bookshelf_id": 2})),
        SimpleNamespace(rowcount=1),
    ]

    result = await Bookshelves.add("alice", "3", "42", edition_id=7)

    assert result == 1
    assert db_connection.execute.await_count == 3
    _, _, update_call = db_connection.execute.await_args_list
    assert update_call.args[0].startswith("UPDATE bookshelves_books SET bookshelf_id")
    assert update_call.args[1] == {"work_id": 42, "username": "alice", "bookshelf_id": 3, "edition_id": 7}


@pytest.mark.asyncio
async def test_remove_uses_optional_shelf_filter(helpers):
    helpers.fetch_all.return_value = [{"?column?": 1}]

    result = await Bookshelves.remove("alice", "42", "2")

    assert result == 1
    (query, params), _kwargs = helpers.fetch_all.await_args
    assert "bookshelf_id = %(bookshelf_id)s" in query
    assert params == {"username": "alice", "work_id": 42, "bookshelf_id": 2}


@pytest.mark.asyncio
async def test_work_summary_includes_all_preset_shelves(helpers):
    helpers.fetch_all.return_value = [{"bookshelf_id": 2, "user_count": 3}]

    summary = await Bookshelves.get_work_summary("42")

    assert summary == {"want_to_read": 0, "currently_reading": 3, "already_read": 0, "stopped_reading": 0}


@pytest.mark.asyncio
async def test_delete_events_by_username_and_work():
    with patch("openlibrary.core.bookshelves_events.execute", new_callable=AsyncMock) as execute:
        await BookshelvesEvents.delete_by_username_and_work("alice", "42")

    (query, params), _kwargs = execute.await_args
    assert query == "DELETE FROM bookshelves_events WHERE username = %(username)s AND work_id = %(work_id)s"
    assert params == {"username": "alice", "work_id": 42}


@pytest.mark.integration
class TestBookshelvesIntegration:
    @pytest.mark.asyncio
    async def test_add_move_remove_and_summary(self, pg_db):
        assert await Bookshelves.add("alice", "1", "42", edition_id=7) == 1
        assert await Bookshelves.get_users_read_status_of_work("alice", 42) == 1

        assert await Bookshelves.add("alice", "3", "42", edition_id=9) == 1
        assert await Bookshelves.get_users_read_status_of_work("alice", 42) == 3
        assert await async_db.fetch_val("SELECT edition_id FROM bookshelves_books WHERE username = 'alice' AND work_id = 42") == 9

        await Bookshelves.add("bob", "3", "42")
        assert await Bookshelves.get_work_summary("42") == {"want_to_read": 0, "currently_reading": 0, "already_read": 2, "stopped_reading": 0}

        assert await Bookshelves.remove("alice", "42", "3") == 1
        assert await Bookshelves.get_users_read_status_of_work("alice", 42) is None
        assert await Bookshelves.remove("alice", "42", "3") is None

    @pytest.mark.asyncio
    async def test_delete_events_by_username_and_work(self, pg_db):
        await BookshelvesEvents.create_event("alice", 42, None, "2026-10-22", event_type=BookshelfEvent.START)
        await BookshelvesEvents.create_event("alice", 43, None, "2026-10-22", event_type=BookshelfEvent.START)
        await BookshelvesEvents.create_event("bob", 42, None, "2026-10-22", event_type=BookshelfEvent.START)

        await BookshelvesEvents.delete_by_username_and_work("alice", 42)
        assert await async_db.fetch_val("SELECT count(*) FROM bookshelves_events WHERE username = 'alice' AND work_id = 42") == 0
        assert await async_db.fetch_val("SELECT count(*) FROM bookshelves_events") == 2

    @pytest.mark.asyncio
    async def test_concurrent_adds_do_not_conflict(self, pg_db):
        results = await asyncio.gather(*(Bookshelves.add("alice", "3", "42", edition_id=edition_id) for edition_id in range(5)))

        assert results == [1] * 5
        assert await async_db.fetch_val("SELECT count(*) FROM bookshelves_books WHERE username = 'alice' AND work_id = 42") == 1

    @pytest.mark.asyncio
    async def test_add_to_reading_log_preserves_custom_shelf_membership(self, pg_db):
        custom_shelf_id = await async_db.fetch_val("INSERT INTO bookshelves (name) VALUES ('Custom') RETURNING id")
        await async_db.execute(
            "INSERT INTO bookshelves_books (username, bookshelf_id, work_id) VALUES (%(username)s, %(bookshelf_id)s, %(work_id)s)",
            {"username": "alice", "bookshelf_id": custom_shelf_id, "work_id": 42},
        )

        assert await Bookshelves.add("alice", "2", "42", edition_id=7) == 1
        shelf_ids = await async_db.fetch_all(
            "SELECT bookshelf_id FROM bookshelves_books WHERE username = %(username)s AND work_id = %(work_id)s",
            {"username": "alice", "work_id": 42},
        )
        assert {row["bookshelf_id"] for row in shelf_ids} == {custom_shelf_id, 2}
