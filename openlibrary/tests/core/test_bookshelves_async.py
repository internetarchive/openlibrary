"""Unit and integration tests for the async Bookshelves batch queries. See ``docs/core/database.md``."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

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
async def test_get_users_read_status_of_works_coerces_string_olids(helpers):
    helpers.fetch_all.return_value = []

    assert await Bookshelves.get_users_read_status_of_works("alice", ["1", "2"]) == []
    (_query, params), _kwargs = helpers.fetch_all.await_args
    assert params == {"username": "alice", "work_ids": [1, 2]}


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
        # String OLIDs from routes behave exactly like ints.
        assert await Bookshelves.get_users_read_status_of_works("alice", ["1", "3"]) == [{"work_id": 1, "bookshelf_id": 3}]
        assert await Bookshelves.get_users_read_status_of_works("nobody", [1, 2, 3]) == []
