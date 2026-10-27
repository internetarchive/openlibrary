"""Unit and integration tests for the async Bookshelves queries. See ``docs/core/database.md``."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import web

from openlibrary.core import async_db
from openlibrary.core.bookshelves import Bookshelves


@pytest.fixture
def helpers():
    with patch("openlibrary.core.bookshelves.fetch_all", new_callable=AsyncMock) as fetch_all:
        yield SimpleNamespace(fetch_all=fetch_all)


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
