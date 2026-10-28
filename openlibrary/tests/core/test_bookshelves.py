"""Unit and integration tests for the Bookshelves model. See ``docs/core/database.md``."""

import asyncio
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
async def test_most_logged_editions_counts_shelvings_that_name_an_edition(helpers):
    helpers.fetch_all.return_value = [{"edition_id": 1, "work_id": 2, "readers": 3}]
    assert await Bookshelves.most_logged_editions(10) == [{"edition_id": 1, "work_id": 2, "readers": 3}]
    (query, params), _kwargs = helpers.fetch_all.await_args
    assert "WHERE edition_id IS NOT NULL GROUP BY edition_id, work_id ORDER BY readers DESC" in query
    assert params == {"limit": 10}


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

    result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, checkin_year=2023, sort="title")

    query, params = fetch_all.await_args.args
    assert "e.event_date LIKE %(checkin_year)s" in query
    assert params["checkin_year"] == "2023%"
    assert result.sort == "created desc"


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


def _fake_solr_sort(sorted_keys: list[str], partial: bool = False) -> AsyncMock:
    """Stands in for run_solr_query_async: Solr has a sort value for `sorted_keys`, in that order."""

    async def run_solr_query_async(*, rows, offset=None, **kwargs):
        start = offset or 0
        return MagicMock(
            error=None,
            num_found=len(sorted_keys),
            docs=[{"key": key} for key in sorted_keys[start : start + rows]],
            raw_resp={"responseHeader": {"partialResults": True} if partial else {}},
        )

    return AsyncMock(side_effect=run_solr_query_async)


@pytest.mark.asyncio
async def test_get_users_logged_books_sorts_with_solr(mock_reading_log_dependencies):
    fetch_all, solr = mock_reading_log_dependencies
    fetch_all.return_value = [{"work_id": i, "created": datetime(2025, 1, i), "edition_id": None} for i in (5, 4, 3, 2, 1)]
    solr.get_many_async = AsyncMock(side_effect=lambda keys, fields: [_solr_doc(int(key[len("/works/OL") : -1])) for key in keys])
    run_solr_query = _fake_solr_sort(["/works/OL2W", "/works/OL4W", "/works/OL5W"])
    with patch("openlibrary.plugins.worksearch.code.run_solr_query_async", run_solr_query):
        pages = [await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, limit=2, page=page, sort="old") for page in (1, 2, 3)]

    assert [[doc.key for doc in page.docs] for page in pages] == [
        ["/works/OL2W", "/works/OL4W"],
        ["/works/OL5W", "/works/OL3W"],
        ["/works/OL1W"],
    ]
    assert all(page.sort == "old" for page in pages)
    query, _ = fetch_all.await_args.args
    assert "ORDER BY created DESC, work_id DESC" in query
    assert "LIMIT" not in query

    first_page_query, *later_queries = run_solr_query.await_args_list
    assert first_page_query.kwargs["sort"] == "old,key"
    assert first_page_query.kwargs["rows"] == 2
    assert first_page_query.kwargs["offset"] == 0
    assert first_page_query.kwargs["spellcheck_count"] == 0
    assert first_page_query.kwargs["request_label"] == "READING_LOG_SORT"
    assert first_page_query.kwargs["extra_params"] == [
        ("fq", "{!terms f=key}/works/OL5W,/works/OL4W,/works/OL3W,/works/OL2W,/works/OL1W"),
        ("fq", "first_publish_year:[* TO *]"),
    ]
    assert [(call.kwargs["offset"], call.kwargs["rows"]) for call in later_queries if "sort" in call.kwargs] == [(2, 2), (4, 2)]
    assert [call.kwargs["rows"] for call in later_queries if "sort" not in call.kwargs] == [3, 3]


@pytest.mark.asyncio
async def test_get_users_logged_books_title_sort_keeps_every_book(mock_reading_log_dependencies):
    run_solr_query = _fake_solr_sort(["/works/OL42W"])
    with patch("openlibrary.plugins.worksearch.code.run_solr_query_async", run_solr_query):
        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, sort="title")

    assert [doc.key for doc in result.docs] == ["/works/OL42W"]
    assert run_solr_query.await_args.kwargs["extra_params"] == [("fq", "{!terms f=key}/works/OL42W")]
    run_solr_query.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [{"msg": "Solr is down"}, None])
async def test_get_users_logged_books_falls_back_to_date_added_when_solr_fails(mock_reading_log_dependencies, caplog, error):
    fetch_all, solr = mock_reading_log_dependencies
    fetch_all.return_value = [{"work_id": i, "created": datetime(2025, 1, i), "edition_id": None} for i in (3, 2, 1)]
    solr.get_many_async = AsyncMock(side_effect=lambda keys, fields: [_solr_doc(int(key[len("/works/OL") : -1])) for key in keys])
    solr_response = MagicMock(error=error, num_found=None, docs=[])
    with patch("openlibrary.plugins.worksearch.code.run_solr_query_async", new_callable=AsyncMock, return_value=solr_response):
        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, limit=2, page=1, sort="want_to_read")

    assert [doc.key for doc in result.docs] == ["/works/OL3W", "/works/OL2W"]
    assert result.sort == "created desc"
    assert "falling back to date added" in caplog.text


@pytest.mark.asyncio
async def test_get_users_logged_books_falls_back_to_date_added_on_partial_solr_results(mock_reading_log_dependencies, caplog):
    fetch_all, solr = mock_reading_log_dependencies
    fetch_all.return_value = [{"work_id": i, "created": datetime(2025, 1, i), "edition_id": None} for i in (3, 2, 1)]
    solr.get_many_async = AsyncMock(side_effect=lambda keys, fields: [_solr_doc(int(key[len("/works/OL") : -1])) for key in keys])
    with patch("openlibrary.plugins.worksearch.code.run_solr_query_async", _fake_solr_sort(["/works/OL1W"], partial=True)):
        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, limit=2, page=1, sort="title")

    assert [doc.key for doc in result.docs] == ["/works/OL3W", "/works/OL2W"]
    assert result.sort == "created desc"
    assert "partial results" in caplog.text


@pytest.mark.asyncio
async def test_get_users_logged_books_solr_sort_on_empty_shelf(mock_reading_log_dependencies):
    fetch_all, solr = mock_reading_log_dependencies
    fetch_all.return_value = []
    solr.get_many_async.return_value = []
    with patch("openlibrary.plugins.worksearch.code.run_solr_query_async", new_callable=AsyncMock) as run_solr_query:
        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, sort="title")

    assert result.docs == []
    assert result.sort == "title"
    run_solr_query.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_users_logged_books_sorts_by_own_rating_in_db(mock_reading_log_dependencies):
    fetch_all, _ = mock_reading_log_dependencies
    with patch("openlibrary.plugins.worksearch.code.run_solr_query_async", new_callable=AsyncMock) as run_solr_query:
        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=3, limit=25, page=2, sort="rating")

    query, params = fetch_all.await_args.args
    assert "LEFT JOIN ratings r ON r.username = b.username AND r.work_id = b.work_id" in query
    assert "ORDER BY r.rating DESC NULLS LAST, b.created DESC" in query
    assert "LIMIT %(limit)s OFFSET %(offset)s" in query
    assert params["offset"] == 25
    assert result.sort == "rating"
    run_solr_query.assert_not_awaited()


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
    async def test_rating_sort_uses_the_patrons_own_ratings(self, pg_db, monkeypatch):
        await async_db.execute(
            "INSERT INTO bookshelves_books (username, bookshelf_id, work_id, created) "
            "VALUES ('alice', 3, 1, '2025-01-01'), ('alice', 3, 2, '2025-01-02'), ('alice', 3, 3, '2025-01-03'), ('alice', 3, 4, '2025-01-04')"
        )
        await async_db.execute("INSERT INTO ratings (username, work_id, rating) VALUES ('alice', 1, 2), ('alice', 2, 5), ('bob', 3, 5), ('bob', 1, 1)")
        solr = MagicMock()

        async def get_many(keys, *, fields):
            return [_solr_doc(int(key.split("OL")[1].split("W")[0])) for key in keys]

        solr.get_many_async = AsyncMock(side_effect=get_many)
        monkeypatch.setattr("openlibrary.core.bookshelves.get_solr", lambda: solr)
        monkeypatch.setattr(Bookshelves, "add_storage_items_for_redirects", AsyncMock())
        monkeypatch.setattr(Bookshelves, "link_editions_to_works", lambda docs: docs)

        pages = [await Bookshelves.get_users_logged_books("alice", bookshelf_id=3, limit=3, page=page, sort="rating") for page in (1, 2)]

        assert [[doc.key for doc in page.docs] for page in pages] == [["/works/OL2W", "/works/OL1W", "/works/OL4W"], ["/works/OL3W"]]

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
async def test_work_summary_includes_all_preset_shelves(helpers):
    helpers.fetch_all.return_value = [{"bookshelf_id": 2, "user_count": 3}]

    summary = await Bookshelves.get_work_summary("42")

    assert summary == {"want_to_read": 0, "currently_reading": 3, "already_read": 0, "stopped_reading": 0}


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
