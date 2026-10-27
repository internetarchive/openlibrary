"""Unit and integration tests for the async Bookshelves queries. See ``docs/core/database.md``."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import web

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


# --- Unit tests (no postgres required) ------------------------------------------


@pytest.mark.asyncio
async def test_get_users_read_status_of_works_uses_any(helpers):
    helpers.fetch_all.return_value = [{"work_id": 1, "bookshelf_id": 3}]

    result = await Bookshelves.get_users_read_status_of_works("alice", [1, 2, 3])

    assert result == [{"work_id": 1, "bookshelf_id": 3}]
    (query, params), _kwargs = helpers.fetch_all.await_args
    assert "work_id = ANY(%(work_ids)s)" in query
    assert params == {"username": "alice", "work_ids": [1, 2, 3]}


@pytest.mark.asyncio
async def test_get_users_read_status_of_works_empty_skips_query(helpers):
    assert await Bookshelves.get_users_read_status_of_works("alice", []) == []
    helpers.fetch_all.assert_not_awaited()


# --- Integration tests (real postgres, marked `integration`) -------------------


@pytest.mark.integration
class TestBookshelvesReadStatusIntegration:
    @pytest.mark.asyncio
    async def test_batch_read_status(self, pg_db):
        rows = [("alice", 1, 3), ("alice", 2, 1), ("bob", 3, 3)]
        for username, work_id, bookshelf_id in rows:
            await async_db.execute(
                "INSERT INTO bookshelves_books (username, work_id, bookshelf_id) VALUES (%(username)s, %(work_id)s, %(bookshelf_id)s)",
                {"username": username, "work_id": work_id, "bookshelf_id": bookshelf_id},
            )

        result = await Bookshelves.get_users_read_status_of_works("alice", [1, 2, 3])
        assert sorted(result, key=lambda row: row["work_id"]) == [
            {"work_id": 1, "bookshelf_id": 3},
            {"work_id": 2, "bookshelf_id": 1},
        ]
        assert await Bookshelves.get_users_read_status_of_works("nobody", [1, 2, 3]) == []


# --- Public reading log -------------------------------------------------------


def _solr_doc(work_id: int) -> web.storage:
    return web.storage(key=f"/works/OL{work_id}W", title=f"Work {work_id}")


@pytest.fixture
def mock_reading_log_dependencies():
    rows = [{"work_id": 42, "created": datetime(2025, 1, 2), "edition_id": 73}]
    solr = MagicMock()
    solr.get_many_async = AsyncMock(return_value=[_solr_doc(42)])
    with (
        patch("openlibrary.core.bookshelves.fetch_all", new_callable=AsyncMock, return_value=rows) as fetch_all,
        patch("openlibrary.core.bookshelves.get_solr", return_value=solr),
        patch.object(Bookshelves, "count_total_books_logged_by_user_per_shelf", new_callable=AsyncMock, return_value={1: 1}),
        patch.object(Bookshelves, "add_storage_items_for_redirects", new_callable=AsyncMock),
        patch.object(Bookshelves, "link_editions_to_works", side_effect=lambda docs: docs),
    ):
        yield fetch_all, solr


@pytest.mark.asyncio
async def test_count_total_books_logged_by_user_per_shelf_uses_async_query():
    rows = [{"bookshelf_id": 1, "count": 2}, {"bookshelf_id": 3, "count": 5}]
    with patch("openlibrary.core.bookshelves.fetch_all", new_callable=AsyncMock, return_value=rows) as fetch_all:
        counts = await Bookshelves.count_total_books_logged_by_user_per_shelf("alice")

    assert counts == {1: 2, 3: 5}
    query, params = fetch_all.await_args.args
    assert "bookshelf_id = ANY(%(bookshelf_ids)s)" in query
    assert params == {"username": "alice", "bookshelf_ids": [1, 2, 3, 4]}


@pytest.mark.asyncio
async def test_count_total_books_logged_by_user_per_shelf_accepts_string_ids():
    with patch("openlibrary.core.bookshelves.fetch_all", new_callable=AsyncMock, return_value=[]) as fetch_all:
        await Bookshelves.count_total_books_logged_by_user_per_shelf("alice", bookshelf_ids=["1", "4"])

    _, params = fetch_all.await_args.args
    assert params["bookshelf_ids"] == [1, 4]


@pytest.mark.asyncio
async def test_get_users_logged_books_uses_async_sorted_query(mock_reading_log_dependencies):
    fetch_all, solr = mock_reading_log_dependencies

    result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, limit=25, page=2, sort="created asc")

    assert result.username == "alice"
    assert result.total_results == 1
    assert result.docs[0].key == "/works/OL42W"
    assert result.docs[0].logged_date == datetime(2025, 1, 2)
    assert result.docs[0].logged_edition == "/books/OL73M"
    query, params = fetch_all.await_args.args
    assert "ORDER BY created ASC" in query
    assert "LIMIT %(limit)s OFFSET %(offset)s" in query
    assert params["offset"] == 25
    solr.get_many_async.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_users_logged_books_preserves_null_edition(mock_reading_log_dependencies):
    fetch_all, solr = mock_reading_log_dependencies
    fetch_all.return_value = [{"work_id": 42, "created": datetime(2025, 1, 2), "edition_id": None}]

    result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1)

    assert result.docs[0].logged_edition == ""
    solr.get_many_async.assert_awaited_once()
    assert solr.get_many_async.await_args.args[0] == ["/works/OL42W"]


@pytest.mark.asyncio
async def test_get_users_logged_books_binds_checkin_year_as_pattern(mock_reading_log_dependencies):
    fetch_all, _ = mock_reading_log_dependencies

    await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, checkin_year=2023)

    query, params = fetch_all.await_args.args
    assert "e.event_date LIKE %(checkin_year)s" in query
    assert params["checkin_year"] == "2023%"


@pytest.mark.asyncio
async def test_get_users_logged_books_uses_async_query_when_filtering(mock_reading_log_dependencies):
    fetch_all, _ = mock_reading_log_dependencies
    solr_response = MagicMock(num_found=1, docs=[_solr_doc(42)])
    with patch("openlibrary.plugins.worksearch.code.run_solr_query_async", new_callable=AsyncMock, return_value=solr_response) as run_solr_query:
        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, q="title")

    assert result.total_results == 1
    assert result.docs[0].logged_edition == "/books/OL73M"
    query, params = fetch_all.await_args.args
    assert "WHERE bookshelf_id = %(bookshelf_id)s AND username = %(username)s" in query
    assert "LIMIT" not in query
    assert params["username"] == "alice"
    run_solr_query.assert_awaited_once()


class TestPublicReadingLogIntegration:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_sorted_reading_log_and_shelf_counts(self, pg_db, monkeypatch):
        await async_db.execute(
            "INSERT INTO bookshelves_books (username, bookshelf_id, work_id, edition_id, created) "
            "VALUES ('alice', 1, 42, 73, '2025-01-02'), ('alice', 1, 43, NULL, '2025-01-01'), ('alice', 2, 44, 74, '2024-01-01')"
        )

        solr = MagicMock()

        async def get_many(keys, *, fields):
            return [_solr_doc(int(key.split("OL")[1].split("W")[0])) for key in keys if key.startswith("/works/")]

        solr.get_many_async = AsyncMock(side_effect=get_many)
        monkeypatch.setattr("openlibrary.core.bookshelves.get_solr", lambda: solr)
        monkeypatch.setattr(Bookshelves, "add_storage_items_for_redirects", AsyncMock())
        monkeypatch.setattr(Bookshelves, "link_editions_to_works", lambda docs: docs)

        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, limit=1, page=1)

        assert result.total_results == 2
        assert result.shelf_totals == {1: 2, 2: 1}
        assert [doc.key for doc in result.docs] == ["/works/OL42W"]
        assert result.docs[0].logged_edition == "/books/OL73M"
        assert await Bookshelves.count_user_books_on_shelf("alice", 1) == 2

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_checkin_year_query_returns_matching_books(self, pg_db, monkeypatch):
        await async_db.execute("INSERT INTO bookshelves_books (username, bookshelf_id, work_id, edition_id) VALUES ('alice', 3, 42, 73)")
        await async_db.execute(
            "INSERT INTO bookshelves_events (username, work_id, edition_id, event_type, event_date) "
            "VALUES ('alice', 42, 73, 1, '2023-06-01'), ('alice', 43, 74, 1, '2022-06-01')"
        )
        solr = MagicMock()
        solr.get_many_async = AsyncMock(return_value=[_solr_doc(42)])
        monkeypatch.setattr("openlibrary.core.bookshelves.get_solr", lambda: solr)
        monkeypatch.setattr(Bookshelves, "add_storage_items_for_redirects", AsyncMock())
        monkeypatch.setattr(Bookshelves, "link_editions_to_works", lambda docs: docs)

        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=3, checkin_year=2023)

        assert [doc.key for doc in result.docs] == ["/works/OL42W"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_filtered_reading_log_query_uses_postgres_parameters(self, pg_db, monkeypatch):
        await async_db.execute("INSERT INTO bookshelves_books (username, bookshelf_id, work_id, edition_id) VALUES ('alice', 1, 42, 73)")
        solr_response = MagicMock(num_found=1, docs=[_solr_doc(42)])
        monkeypatch.setattr("openlibrary.plugins.worksearch.code.run_solr_query_async", AsyncMock(return_value=solr_response))
        solr = MagicMock()
        solr.get_many_async = AsyncMock(return_value=[])
        monkeypatch.setattr("openlibrary.core.bookshelves.get_solr", lambda: solr)
        monkeypatch.setattr(Bookshelves, "link_editions_to_works", lambda docs: docs)

        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, q="title")

        assert result.total_results == 1
        assert [doc.key for doc in result.docs] == ["/works/OL42W"]


@pytest.fixture
def db_connection():
    conn = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(rowcount=0),
                SimpleNamespace(rowcount=0),
                SimpleNamespace(rowcount=1),
            ]
        )
    )

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
    lock_call, update_call, insert_call = db_connection.execute.await_args_list
    assert lock_call.args == (
        "SELECT pg_advisory_xact_lock(hashtext(%(username)s), %(work_id)s)",
        {"username": "alice", "work_id": 42},
    )
    assert update_call.args[0].startswith("UPDATE bookshelves_books SET bookshelf_id")
    assert "bookshelf_id = ANY(%(preset_bookshelf_ids)s)" in update_call.args[0]
    assert update_call.args[1]["preset_bookshelf_ids"] == [1, 2, 3, 4]
    assert "ON CONFLICT (username, work_id, bookshelf_id) DO UPDATE" in insert_call.args[0]
    assert "RETURNING 1" not in insert_call.args[0]
    assert insert_call.args[1] == {"work_id": 42, "username": "alice", "bookshelf_id": 2, "edition_id": 7}


@pytest.mark.asyncio
async def test_add_updates_existing_shelf(db_connection):
    db_connection.execute.side_effect = [
        SimpleNamespace(rowcount=0),
        SimpleNamespace(rowcount=1),
    ]

    result = await Bookshelves.add("alice", "3", "42", edition_id=7)

    assert result == 1
    assert db_connection.execute.await_count == 2
    _, update_call = db_connection.execute.await_args_list
    assert update_call.args[0].startswith("UPDATE bookshelves_books SET bookshelf_id")
    assert "bookshelf_id = ANY(%(preset_bookshelf_ids)s)" in update_call.args[0]
    assert update_call.args[1] == {
        "work_id": 42,
        "username": "alice",
        "bookshelf_id": 3,
        "edition_id": 7,
        "preset_bookshelf_ids": [1, 2, 3, 4],
    }


@pytest.mark.asyncio
async def test_remove_uses_optional_shelf_filter_and_deletes_events(db_connection):
    db_connection.execute.side_effect = [SimpleNamespace(rowcount=1), SimpleNamespace(rowcount=2)]

    result = await Bookshelves.remove("alice", "42", "2")

    assert result == 1
    assert db_connection.execute.await_count == 2
    (query, params), _kwargs = db_connection.execute.await_args_list[0]
    assert "bookshelf_id = %(bookshelf_id)s" in query
    assert params == {"username": "alice", "work_id": 42, "bookshelf_id": 2}
    event_query, event_params = db_connection.execute.await_args_list[1].args
    assert event_query == "DELETE FROM bookshelves_events WHERE username = %(username)s AND work_id = %(work_id)s"
    assert event_params == {"username": "alice", "work_id": 42}


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

        await BookshelvesEvents.create_event("alice", 42, 7, "2026-10-22", event_type=BookshelfEvent.START)
        assert await Bookshelves.remove("alice", "42", "3") == 1
        assert await Bookshelves.get_users_read_status_of_work("alice", 42) is None
        assert await async_db.fetch_val("SELECT count(*) FROM bookshelves_events WHERE username = 'alice' AND work_id = 42") == 0
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
        results = await asyncio.gather(*(Bookshelves.add("alice", str(shelf_id), "42") for shelf_id in [1, 2, 3, 4]))

        assert results == [1] * 4
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
