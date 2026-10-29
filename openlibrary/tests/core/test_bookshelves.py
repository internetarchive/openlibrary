"""Unit and integration tests for the Bookshelves model. See ``docs/core/database.md``."""

import asyncio
from collections.abc import Collection
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import web

from openlibrary.core import async_db
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents
from openlibrary.core.cache import MemoryCache

READABLE_ONLY = ["ebook_access:[borrowable TO *]"]


@pytest.fixture
def helpers():
    with (
        patch("openlibrary.core.bookshelves.fetch_all", new_callable=AsyncMock) as fetch_all,
        patch("openlibrary.core.bookshelves.fetch_val", new_callable=AsyncMock) as fetch_val,
    ):
        yield SimpleNamespace(fetch_all=fetch_all, fetch_val=fetch_val)


@pytest.fixture(autouse=True)
def memcache():
    """A cache per test, so a shelf order cached by one test can't leak into the next."""
    with patch("openlibrary.core.cache.get_memcache", return_value=MemoryCache()):
        yield


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


def _solr_docs(keys, fields) -> list[web.storage]:
    """Stands in for get_many_async: Solr has every work asked for, and no editions."""
    return [_solr_doc(int(key[len("/works/OL") : -1])) for key in keys if key.startswith("/works/")]


def _shelf(*work_ids: int) -> list[dict]:
    """Rows for a shelf holding `work_ids`, newest added first."""
    return [{"work_id": work_id, "created": datetime(2025, 1, work_id), "edition_id": None} for work_id in work_ids]


def _shelf_queries(shelf: list[dict]):
    """Stands in for fetch_all on a shelf holding `shelf`, newest added first."""

    async def fetch_all(query, params):
        if "ANY(%(work_ids)s)" in query:
            return [book for book in shelf if book["work_id"] in params["work_ids"]]
        if "LIMIT" in query:
            return shelf[params["offset"] : params["offset"] + params["limit"]]
        return shelf

    return fetch_all


def _fake_solr(sorted_keys: list[str], readable: Collection[str] = (), partial: bool = False) -> AsyncMock:
    """
    Stands in for run_solr_query_async over the works in its {!terms f=key} filter: Solr has a
    sort value for `sorted_keys`, in that order, and `readable` pass the Readable Only filter.
    """

    async def run_solr_query_async(*, rows, extra_params, sort=None, **kwargs):
        (_, terms), *filters = extra_params
        keys = terms.removeprefix("{!terms f=key}").split(",")
        if ("fq", READABLE_ONLY[0]) in filters:
            keys = [key for key in keys if key in readable]
        if sort:
            keys = [key for key in sorted_keys if key in keys]
        return MagicMock(
            error=None,
            num_found=len(keys),
            docs=[{"key": key} for key in keys[:rows]],
            raw_resp={"responseHeader": {"partialResults": True} if partial else {}},
        )

    return AsyncMock(side_effect=run_solr_query_async)


def _shelf_count(count: int):
    """Patches the shelf totals, which set the cache key and the size limit, to `count` books on shelf 1."""
    return patch.object(Bookshelves, "count_total_books_logged_by_user_per_shelf", new_callable=AsyncMock, return_value={1: count})


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


@pytest.mark.asyncio
async def test_get_users_logged_books_sorts_with_solr(mock_reading_log_dependencies):
    fetch_all, solr = mock_reading_log_dependencies
    fetch_all.side_effect = _shelf_queries(_shelf(5, 4, 3, 2, 1))
    solr.get_many_async = AsyncMock(side_effect=_solr_docs)
    run_solr_query = _fake_solr(["/works/OL2W", "/works/OL4W", "/works/OL5W"])
    with _shelf_count(5), patch("openlibrary.plugins.worksearch.code.run_solr_query_async", run_solr_query):
        pages = [await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, limit=2, page=page, sort="old") for page in (1, 2, 3)]

    assert [[doc.key for doc in page.docs] for page in pages] == [
        ["/works/OL2W", "/works/OL4W"],
        ["/works/OL5W", "/works/OL3W"],
        ["/works/OL1W"],
    ]
    assert all(page.sort == "old" and page.total_results == 5 for page in pages)

    run_solr_query.assert_awaited_once()
    solr_query = run_solr_query.await_args.kwargs
    assert solr_query["sort"] == "old,key"
    assert solr_query["rows"] == 5
    assert solr_query["fields"] == ["key"]
    assert solr_query["spellcheck_count"] == 0
    assert solr_query["request_label"] == "READING_LOG_SORT"
    assert solr_query["extra_params"] == [
        ("fq", "{!terms f=key}/works/OL5W,/works/OL4W,/works/OL3W,/works/OL2W,/works/OL1W"),
        ("fq", "first_publish_year:[* TO *]"),
    ]
    (shelf_query, _), *page_queries = [call.args for call in fetch_all.await_args_list]
    assert "ORDER BY created DESC, work_id DESC" in shelf_query
    assert "LIMIT" not in shelf_query
    assert [params["work_ids"] for _, params in page_queries] == [[2, 4], [5, 3], [1]]


@pytest.mark.asyncio
async def test_get_users_logged_books_title_sort_keeps_every_book(mock_reading_log_dependencies):
    run_solr_query = _fake_solr(["/works/OL42W"])
    with patch("openlibrary.plugins.worksearch.code.run_solr_query_async", run_solr_query):
        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, sort="title")

    assert [doc.key for doc in result.docs] == ["/works/OL42W"]
    assert run_solr_query.await_args.kwargs["extra_params"] == [("fq", "{!terms f=key}/works/OL42W")]
    run_solr_query.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [{"msg": "Solr is down"}, None])
async def test_get_users_logged_books_falls_back_to_date_added_when_solr_fails(mock_reading_log_dependencies, caplog, error):
    fetch_all, solr = mock_reading_log_dependencies
    fetch_all.side_effect = _shelf_queries(_shelf(3, 2, 1))
    solr.get_many_async = AsyncMock(side_effect=_solr_docs)
    solr_response = MagicMock(error=error, num_found=None, docs=[])
    with patch("openlibrary.plugins.worksearch.code.run_solr_query_async", new_callable=AsyncMock, return_value=solr_response) as run_solr_query:
        results = [await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, limit=2, page=1, sort="want_to_read") for _ in range(2)]

    assert all([doc.key for doc in result.docs] == ["/works/OL3W", "/works/OL2W"] for result in results)
    assert all(result.sort == "created desc" for result in results)
    assert "Reading log sort 'want_to_read'" in caplog.text
    assert run_solr_query.await_count == 2


@pytest.mark.asyncio
async def test_get_users_logged_books_falls_back_to_date_added_on_partial_solr_results(mock_reading_log_dependencies, caplog):
    fetch_all, solr = mock_reading_log_dependencies
    fetch_all.side_effect = _shelf_queries(_shelf(3, 2, 1))
    solr.get_many_async = AsyncMock(side_effect=_solr_docs)
    with patch("openlibrary.plugins.worksearch.code.run_solr_query_async", _fake_solr(["/works/OL1W"], partial=True)):
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


@pytest.mark.asyncio
async def test_get_users_logged_books_reuses_the_order_until_the_shelf_count_changes(mock_reading_log_dependencies):
    run_solr_query = _fake_solr(["/works/OL42W"])
    with patch("openlibrary.plugins.worksearch.code.run_solr_query_async", run_solr_query):
        for _ in range(2):
            await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, sort="title")
        run_solr_query.assert_awaited_once()

        with _shelf_count(2):
            await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, sort="title")
        assert run_solr_query.await_count == 2


@pytest.mark.asyncio
async def test_get_users_logged_books_skips_books_that_left_the_shelf_after_it_was_sorted(mock_reading_log_dependencies):
    fetch_all, solr = mock_reading_log_dependencies
    shelf = _shelf(3, 2, 1)
    fetch_all.side_effect = _shelf_queries(shelf)
    solr.get_many_async = AsyncMock(side_effect=_solr_docs)
    with _shelf_count(3), patch("openlibrary.plugins.worksearch.code.run_solr_query_async", _fake_solr(["/works/OL1W", "/works/OL2W", "/works/OL3W"])):
        await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, limit=2, sort="title")
        del shelf[1]
        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, limit=2, sort="title")

    assert [doc.key for doc in result.docs] == ["/works/OL1W"]


@pytest.mark.asyncio
async def test_get_users_logged_books_sorts_huge_shelves_by_date_added(mock_reading_log_dependencies):
    fetch_all, _ = mock_reading_log_dependencies
    with (
        _shelf_count(Bookshelves.MAX_SOLR_ORDERED_SHELF_SIZE + 1),
        patch("openlibrary.plugins.worksearch.code.run_solr_query_async", new_callable=AsyncMock) as run_solr_query,
    ):
        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, sort="title")

    assert result.sort == "created desc"
    query, _ = fetch_all.await_args.args
    assert "ORDER BY created DESC LIMIT" in query
    run_solr_query.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_users_logged_books_sorts_a_filtered_shelf_by_date_added(mock_reading_log_dependencies):
    fetch_all, solr = mock_reading_log_dependencies
    fetch_all.side_effect = _shelf_queries(_shelf(5, 4, 3, 2, 1))
    solr.get_many_async = AsyncMock(side_effect=_solr_docs)
    run_solr_query = _fake_solr([], readable={"/works/OL4W", "/works/OL2W", "/works/OL1W"})
    with _shelf_count(5), patch("openlibrary.plugins.worksearch.code.run_solr_query_async", run_solr_query):
        pages = [await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, limit=2, page=page, fq=READABLE_ONLY) for page in (1, 2)]

    assert [[doc.key for doc in page.docs] for page in pages] == [["/works/OL4W", "/works/OL2W"], ["/works/OL1W"]]
    assert all(page.sort == "created desc" and page.total_results == 3 for page in pages)
    run_solr_query.assert_awaited_once()
    assert run_solr_query.await_args.kwargs["sort"] is None
    assert run_solr_query.await_args.kwargs["extra_params"] == [
        ("fq", "{!terms f=key}/works/OL5W,/works/OL4W,/works/OL3W,/works/OL2W,/works/OL1W"),
        ("fq", "ebook_access:[borrowable TO *]"),
    ]


@pytest.mark.asyncio
async def test_get_users_logged_books_sorts_a_filtered_shelf_with_solr(mock_reading_log_dependencies):
    fetch_all, solr = mock_reading_log_dependencies
    fetch_all.side_effect = _shelf_queries(_shelf(5, 4, 3, 2, 1))
    solr.get_many_async = AsyncMock(side_effect=_solr_docs)
    run_solr_query = _fake_solr(["/works/OL2W", "/works/OL4W", "/works/OL5W"], readable={"/works/OL5W", "/works/OL4W", "/works/OL3W", "/works/OL1W"})
    with _shelf_count(5), patch("openlibrary.plugins.worksearch.code.run_solr_query_async", run_solr_query):
        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, sort="old", fq=READABLE_ONLY)

    assert [doc.key for doc in result.docs] == ["/works/OL4W", "/works/OL5W", "/works/OL3W", "/works/OL1W"]
    assert result.sort == "old"
    assert result.total_results == 4
    _, sort_query = run_solr_query.await_args_list
    assert sort_query.kwargs["sort"] == "old,key"
    assert sort_query.kwargs["extra_params"] == [
        ("fq", "{!terms f=key}/works/OL5W,/works/OL4W,/works/OL3W,/works/OL1W"),
        ("fq", "first_publish_year:[* TO *]"),
    ]


@pytest.mark.asyncio
async def test_get_users_logged_books_sorts_a_filtered_shelf_by_own_rating(mock_reading_log_dependencies):
    fetch_all, solr = mock_reading_log_dependencies
    fetch_all.side_effect = _shelf_queries(_shelf(2, 1, 4, 3))
    solr.get_many_async = AsyncMock(side_effect=_solr_docs)
    with _shelf_count(4), patch("openlibrary.plugins.worksearch.code.run_solr_query_async", _fake_solr([], readable={"/works/OL1W", "/works/OL3W"})):
        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, sort="rating", fq=READABLE_ONLY)

    assert [doc.key for doc in result.docs] == ["/works/OL1W", "/works/OL3W"]
    assert result.sort == "rating"
    shelf_query, _ = fetch_all.await_args_list[0].args
    assert "LEFT JOIN ratings r ON r.username = b.username AND r.work_id = b.work_id" in shelf_query
    assert "LIMIT" not in shelf_query


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("q", "checkin_year", "shelf_count"),
    [
        pytest.param("tolkien", None, 1, id="search"),
        pytest.param("", 2023, 1, id="year-page"),
        pytest.param("", None, Bookshelves.MAX_SOLR_ORDERED_SHELF_SIZE + 1, id="huge-shelf"),
    ],
)
async def test_get_users_logged_books_leaves_some_filtered_shelves_in_solr_order(mock_reading_log_dependencies, q, checkin_year, shelf_count):
    solr_response = MagicMock(num_found=1, docs=[_solr_doc(42)])
    with (
        _shelf_count(shelf_count),
        patch("openlibrary.plugins.worksearch.code.run_solr_query_async", new_callable=AsyncMock, return_value=solr_response) as run_solr_query,
    ):
        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, sort="title", q=q, checkin_year=checkin_year, fq=READABLE_ONLY)

    assert result.sort is None
    assert result.total_results == 1
    run_solr_query.assert_awaited_once()
    assert "sort" not in run_solr_query.await_args.kwargs


@pytest.mark.asyncio
async def test_get_users_logged_books_leaves_a_filtered_shelf_in_solr_order_when_sorting_fails(mock_reading_log_dependencies, caplog):
    solr_responses = [MagicMock(error={"msg": "Solr is down"}, num_found=None, docs=[]), MagicMock(num_found=1, docs=[_solr_doc(42)])]
    with patch("openlibrary.plugins.worksearch.code.run_solr_query_async", new_callable=AsyncMock, side_effect=solr_responses) as run_solr_query:
        result = await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, fq=READABLE_ONLY)

    assert result.sort is None
    assert result.docs[0].key == "/works/OL42W"
    assert run_solr_query.await_args.kwargs["rows"] == 100
    assert "Solr is down" in caplog.text


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
    async def test_solr_sorted_shelf_pages_are_slices_of_one_order(self, pg_db, monkeypatch):
        await async_db.execute(
            "INSERT INTO bookshelves_books (username, bookshelf_id, work_id, edition_id, created) "
            "VALUES ('alice', 1, 1, 11, '2025-01-01'), ('alice', 1, 2, NULL, '2025-01-02'), ('alice', 1, 3, NULL, '2025-01-03'), "
            "('bob', 1, 4, NULL, '2025-01-04')"
        )
        solr = MagicMock()
        solr.get_many_async = AsyncMock(side_effect=_solr_docs)
        monkeypatch.setattr("openlibrary.core.bookshelves.get_solr", lambda: solr)
        monkeypatch.setattr("openlibrary.plugins.worksearch.code.run_solr_query_async", _fake_solr(["/works/OL3W", "/works/OL1W"]))
        monkeypatch.setattr(Bookshelves, "add_storage_items_for_redirects", AsyncMock())
        monkeypatch.setattr(Bookshelves, "link_editions_to_works", lambda docs: docs)

        pages = [await Bookshelves.get_users_logged_books("alice", bookshelf_id=1, limit=2, page=page, sort="title") for page in (1, 2)]

        assert [[doc.key for doc in page.docs] for page in pages] == [["/works/OL3W", "/works/OL1W"], ["/works/OL2W"]]
        assert pages[0].docs[1].logged_edition == "/books/OL11M"
        assert pages[0].total_results == 3

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_filtered_shelf_sorted_by_rating(self, pg_db, monkeypatch):
        await async_db.execute(
            "INSERT INTO bookshelves_books (username, bookshelf_id, work_id, created) "
            "VALUES ('alice', 3, 1, '2025-01-01'), ('alice', 3, 2, '2025-01-02'), ('alice', 3, 3, '2025-01-03'), ('alice', 3, 4, '2025-01-04')"
        )
        await async_db.execute("INSERT INTO ratings (username, work_id, rating) VALUES ('alice', 1, 2), ('alice', 2, 5), ('bob', 4, 5)")
        solr = MagicMock()
        solr.get_many_async = AsyncMock(side_effect=_solr_docs)
        monkeypatch.setattr("openlibrary.core.bookshelves.get_solr", lambda: solr)
        monkeypatch.setattr("openlibrary.plugins.worksearch.code.run_solr_query_async", _fake_solr([], readable={"/works/OL1W", "/works/OL2W", "/works/OL4W"}))
        monkeypatch.setattr(Bookshelves, "add_storage_items_for_redirects", AsyncMock())
        monkeypatch.setattr(Bookshelves, "link_editions_to_works", lambda docs: docs)

        pages = [await Bookshelves.get_users_logged_books("alice", bookshelf_id=3, limit=2, page=page, sort="rating", fq=READABLE_ONLY) for page in (1, 2)]

        assert [[doc.key for doc in page.docs] for page in pages] == [["/works/OL2W", "/works/OL1W"], ["/works/OL4W"]]
        assert pages[0].total_results == 3

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
