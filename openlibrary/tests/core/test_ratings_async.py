"""Unit and integration tests for the async Ratings queries. See ``docs/core/database.md``."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core.ratings import Ratings

# --- Unit test (no postgres required) ------------------------------------------


@pytest.fixture
def helpers():
    with (
        patch("openlibrary.core.ratings.fetch_val", new_callable=AsyncMock) as fetch_val,
        patch("openlibrary.core.ratings.fetch_one", new_callable=AsyncMock) as fetch_one,
        patch("openlibrary.core.ratings.fetch_all", new_callable=AsyncMock) as fetch_all,
        patch("openlibrary.core.ratings.execute", new_callable=AsyncMock) as execute,
    ):
        yield SimpleNamespace(fetch_val=fetch_val, fetch_one=fetch_one, fetch_all=fetch_all, execute=execute)


@pytest.mark.asyncio
async def test_get_work_ratings_summary(helpers):
    mock_row = {
        "ratings_count_1": 2,
        "ratings_count_2": 3,
        "ratings_count_3": 5,
        "ratings_count_4": 10,
        "ratings_count_5": 20,
    }
    helpers.fetch_one.return_value = mock_row

    summary = await Ratings.get_work_ratings_summary(123)

    assert summary is not None
    assert summary["ratings_count_1"] == 2
    assert summary["ratings_count_2"] == 3
    assert summary["ratings_count_3"] == 5
    assert summary["ratings_count_4"] == 10
    assert summary["ratings_count_5"] == 20
    assert summary["ratings_count"] == 40
    (query, params), _kwargs = helpers.fetch_one.await_args
    assert "SELECT" in query
    assert "FILTER (WHERE rating = 1)" in query
    assert params == {"work_id": 123}


@pytest.mark.asyncio
async def test_get_work_ratings_summary_none_when_no_ratings(helpers):
    helpers.fetch_one.return_value = None

    summary = await Ratings.get_work_ratings_summary(123)

    assert summary is None


@pytest.mark.asyncio
async def test_remove_rating(helpers):
    await Ratings.remove("alice", 42)

    helpers.execute.assert_awaited_once_with(
        "DELETE FROM ratings WHERE work_id = %(work_id)s AND username = %(username)s",
        {"work_id": 42, "username": "alice"},
    )


@pytest.mark.asyncio
async def test_add_rating_new(helpers):
    with (
        patch("openlibrary.core.bookshelves.Bookshelves.get_users_read_status_of_work", new_callable=AsyncMock) as mock_read_status,
        patch("openlibrary.core.bookshelves.Bookshelves.add", new_callable=AsyncMock),
        patch("openlibrary.core.ratings.Ratings.get_users_rating_for_work", new_callable=AsyncMock) as mock_get_rating,
    ):
        mock_read_status.return_value = None
        mock_get_rating.return_value = None

        await Ratings.add("alice", 42, 5, edition_id=99)

    helpers.execute.assert_awaited()
    (query, params), _kwargs = helpers.execute.await_args
    assert query.startswith("INSERT INTO ratings")
    assert params == {"username": "alice", "work_id": 42, "rating": 5, "edition_id": 99}


@pytest.mark.asyncio
async def test_add_rating_update_existing(helpers):
    with (
        patch("openlibrary.core.bookshelves.Bookshelves.get_users_read_status_of_work", new_callable=AsyncMock) as mock_read_status,
        patch("openlibrary.core.bookshelves.Bookshelves.add", new_callable=AsyncMock),
        patch("openlibrary.core.ratings.Ratings.get_users_rating_for_work", new_callable=AsyncMock) as mock_get_rating,
    ):
        mock_read_status.return_value = 1
        mock_get_rating.return_value = 3

        await Ratings.add("alice", 42, 4)

    helpers.execute.assert_awaited()
    (query, params), _kwargs = helpers.execute.await_args
    assert query.startswith("UPDATE ratings SET rating = %(rating)s")
    assert params == {"username": "alice", "work_id": 42, "rating": 4}


@pytest.mark.asyncio
async def test_add_rating_invalid_rating(helpers):
    result = await Ratings.add("alice", 42, 6)
    assert result is None
    helpers.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_total_num_books_rated(helpers):
    helpers.fetch_val.return_value = 100

    count = await Ratings.total_num_books_rated()

    assert count == 100
    helpers.fetch_val.assert_awaited_once_with("SELECT count(work_id) from ratings", None)


@pytest.mark.asyncio
async def test_total_num_unique_raters(helpers):
    helpers.fetch_val.return_value = 50

    count = await Ratings.total_num_unique_raters()

    assert count == 50
    helpers.fetch_val.assert_awaited_once_with("select count(DISTINCT username) from ratings", None)


# --- Integration tests (require postgres) ----------------------------------------


@pytest.mark.integration
class TestRatingsIntegration:
    @pytest.mark.asyncio
    async def test_create_select_update_delete(self, pg_db):
        await Ratings.add("alice", 100, 5, edition_id=1)

        summary = await Ratings.get_work_ratings_summary(100)
        assert summary is not None
        assert summary["ratings_count"] == 1
        assert summary["ratings_count_5"] == 1

        await Ratings.add("alice", 100, 4)
        summary = await Ratings.get_work_ratings_summary(100)
        assert summary["ratings_count"] == 1
        assert summary["ratings_count_4"] == 1
        assert summary["ratings_count_5"] == 0

        await Ratings.remove("alice", 100)
        summary = await Ratings.get_work_ratings_summary(100)
        assert summary is None

    @pytest.mark.asyncio
    async def test_multiple_users_rate_same_work(self, pg_db):
        await Ratings.add("alice", 200, 5)
        await Ratings.add("bob", 200, 4)
        await Ratings.add("charlie", 200, 5)

        summary = await Ratings.get_work_ratings_summary(200)
        assert summary is not None
        assert summary["ratings_count"] == 3
        assert summary["ratings_count_5"] == 2
        assert summary["ratings_count_4"] == 1


# --- Sync bridge tests -----------------------------------------------------------


@pytest.mark.asyncio
async def test_get_work_ratings_summary_sync_bridge(helpers):
    mock_row = {
        "ratings_count_1": 1,
        "ratings_count_2": 0,
        "ratings_count_3": 0,
        "ratings_count_4": 0,
        "ratings_count_5": 0,
    }
    helpers.fetch_one.return_value = mock_row

    summary = Ratings.get_work_ratings_summary_sync(123)

    assert summary is not None
    assert summary["ratings_count"] == 1
    helpers.fetch_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_sync_bridge(helpers):
    Ratings.remove_sync("alice", 42)
    helpers.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_sync_bridge(helpers):
    with (
        patch("openlibrary.core.bookshelves.Bookshelves.get_users_read_status_of_work", new_callable=AsyncMock) as mock_read_status,
        patch("openlibrary.core.bookshelves.Bookshelves.add", new_callable=AsyncMock),
        patch("openlibrary.core.ratings.Ratings.get_users_rating_for_work", new_callable=AsyncMock) as mock_get_rating,
    ):
        mock_read_status.return_value = None
        mock_get_rating.return_value = None
        Ratings.add_sync("alice", 42, 5)

    helpers.execute.assert_awaited()
