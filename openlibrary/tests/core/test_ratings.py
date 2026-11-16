"""
Tests for openlibrary.core.ratings

The pure functions that compute rating statistics, plus the async Ratings
queries: unit tests patch the ``async_db`` helpers and check query text and
params, and ``TestRatingsIntegration`` runs the same methods against real
postgres. See ``docs/core/database.md`` for the pattern.
"""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core import async_db
from openlibrary.core.ratings import Ratings
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO


class TestAddAutoShelve:
    """Test that rating a book only auto-shelves it as "Already Read" when
    doing so doesn't overwrite an explicit shelf choice."""

    WANT_TO_READ = 1
    CURRENTLY_READING = 2
    ALREADY_READ = 3
    STOPPED_READING = 4

    @pytest.mark.parametrize(
        ("read_status", "should_auto_shelve"),
        [
            (None, True),  # Unshelved books are moved to Already Read
            (WANT_TO_READ, True),  # ... as are Want to Read books
            (CURRENTLY_READING, False),  # Explicit shelf choices are preserved
            (STOPPED_READING, False),
            (ALREADY_READ, False),  # Already there; nothing to do
        ],
    )
    @pytest.mark.asyncio
    async def test_add_only_auto_shelves_unshelved_and_want_to_read(self, read_status, should_auto_shelve):
        with (
            patch("openlibrary.core.bookshelves.Bookshelves.get_users_read_status_of_work", new_callable=AsyncMock, return_value=read_status),
            patch("openlibrary.core.bookshelves.Bookshelves.add", new_callable=AsyncMock) as bookshelves_add,
            patch("openlibrary.core.ratings.execute", new_callable=AsyncMock) as execute,
        ):
            await Ratings.add("testuser", 123, rating=4)

        if should_auto_shelve:
            bookshelves_add.assert_awaited_once_with("testuser", self.ALREADY_READ, 123, edition_id=None)
        else:
            bookshelves_add.assert_not_called()
        # The rating is saved whatever the shelf.
        execute.assert_awaited_once()


class TestComputeSortableRating:
    """Test the Bayesian lower bound ranking algorithm."""

    def test_all_five_stars(self):
        """A book with only 5-star ratings should have a high sortable rating."""
        # 10 ratings, all 5 stars
        # The Bayesian lower bound is conservative, so it won't be 5.0
        result = Ratings.compute_sortable_rating([0, 0, 0, 0, 10])
        assert result > 3.5  # Should be high, but conservative

    def test_mixed_ratings(self):
        """Test with a realistic mix of ratings."""
        # A typical distribution: more 4-5 stars, some lower
        result = Ratings.compute_sortable_rating([2, 1, 3, 15, 25])
        # Should be between 3.5 and 4.5
        assert 3.5 < result < 4.5

    def test_single_rating(self):
        """A book with a single 5-star rating should be penalized."""
        one_five_star = Ratings.compute_sortable_rating([0, 0, 0, 0, 1])
        many_five_stars = Ratings.compute_sortable_rating([0, 0, 0, 0, 100])

        # The book with 100 ratings should rank higher
        assert many_five_stars > one_five_star

    def test_low_ratings(self):
        """Test with mostly low ratings."""
        result = Ratings.compute_sortable_rating([20, 15, 5, 1, 0])
        # Should be low, around 2 or below
        assert result < 2.5

    def test_no_ratings(self):
        """
        A book with no ratings gets a prior estimate (Bayesian default).
        This is a conservative middle-of-the-road rating, not zero.
        """
        result = Ratings.compute_sortable_rating([0, 0, 0, 0, 0])
        # The algorithm returns a prior around 2.0 (middle of 1-5 scale)
        assert 1.5 < result < 2.5

    def test_uniform_distribution(self):
        """
        Test with equal ratings across all stars.

        The Bayesian lower bound is conservative, so even a uniform
        distribution (which averages to 3.0) will give a lower value
        due to the uncertainty penalty.
        """
        result = Ratings.compute_sortable_rating([2, 2, 2, 2, 2])
        # Conservative estimate, lower than the true average of 3.0
        assert 2.0 < result < 3.0

    def test_more_ratings_same_average(self):
        """
        Two books with same average should rank differently based on count.
        More ratings = higher confidence = higher rank.
        """
        # Both have average of 3 stars, but one has more ratings
        few_ratings = Ratings.compute_sortable_rating([0, 0, 10, 0, 0])
        many_ratings = Ratings.compute_sortable_rating([0, 0, 100, 0, 0])

        assert many_ratings > few_ratings


class TestWorkRatingsSummaryFromCounts:
    """Test the ratings summary calculation from rating counts."""

    def test_simple_average(self):
        """Test basic average calculation."""
        result = Ratings.work_ratings_summary_from_counts([0, 0, 0, 0, 10])
        assert result["ratings_average"] == 5.0
        assert result["ratings_count"] == 10
        assert result["ratings_count_5"] == 10

    def test_weighted_average(self):
        """Test average with mixed ratings."""
        # 1 star: 2, 2 star: 1, 3 star: 3, 4 star: 15, 5 star: 25
        # Total: 46, Sum: 2*1 + 1*2 + 3*3 + 15*4 + 25*5 = 2 + 2 + 9 + 60 + 125 = 198
        # Average: 198 / 46 = 4.304...
        result = Ratings.work_ratings_summary_from_counts([2, 1, 3, 15, 25])
        assert abs(result["ratings_average"] - 4.304) < 0.01
        assert result["ratings_count"] == 46

    def test_empty_counts(self):
        """Test with no ratings."""
        result = Ratings.work_ratings_summary_from_counts([0, 0, 0, 0, 0])
        assert result["ratings_average"] == 0.0
        assert result["ratings_count"] == 0
        # Sortable rating uses Bayesian prior when no ratings exist
        assert 1.5 < result["ratings_sortable"] < 2.5

    def test_all_star_counts_preserved(self):
        """Ensure all individual star counts are preserved."""
        result = Ratings.work_ratings_summary_from_counts([5, 4, 3, 2, 1])
        assert result["ratings_count_1"] == 5
        assert result["ratings_count_2"] == 4
        assert result["ratings_count_3"] == 3
        assert result["ratings_count_4"] == 2
        assert result["ratings_count_5"] == 1

    def test_sortable_rating_calculated(self):
        """Verify sortable rating is calculated from counts."""
        result = Ratings.work_ratings_summary_from_counts([0, 0, 0, 0, 10])
        # Should match compute_sortable_rating for same counts
        assert result["ratings_sortable"] == Ratings.compute_sortable_rating([0, 0, 0, 0, 10])


@pytest.fixture
def helpers():
    with (
        patch("openlibrary.core.ratings.fetch_val", new_callable=AsyncMock) as fetch_val,
        patch("openlibrary.core.ratings.fetch_one", new_callable=AsyncMock) as fetch_one,
        patch("openlibrary.core.ratings.fetch_all", new_callable=AsyncMock) as fetch_all,
        patch("openlibrary.core.ratings.execute", new_callable=AsyncMock) as execute,
    ):
        yield SimpleNamespace(fetch_val=fetch_val, fetch_one=fetch_one, fetch_all=fetch_all, execute=execute)


@pytest.fixture
def bookshelves():
    """Patch the async Bookshelves calls made by ``Ratings.add``."""
    with (
        patch("openlibrary.core.bookshelves.Bookshelves.get_users_read_status_of_work", new_callable=AsyncMock, return_value=None) as read_status,
        patch("openlibrary.core.bookshelves.Bookshelves.add", new_callable=AsyncMock) as add,
    ):
        yield SimpleNamespace(read_status=read_status, add=add)


# --- Unit tests (no postgres required) ------------------------------------------


@pytest.mark.asyncio
async def test_get_work_ratings_summary(helpers):
    helpers.fetch_one.return_value = {
        "ratings_count_1": 2,
        "ratings_count_2": 3,
        "ratings_count_3": 5,
        "ratings_count_4": 10,
        "ratings_count_5": 20,
    }

    summary = await Ratings.get_work_ratings_summary(123)

    assert summary is not None
    assert summary["ratings_count_1"] == 2
    assert summary["ratings_count_2"] == 3
    assert summary["ratings_count_3"] == 5
    assert summary["ratings_count_4"] == 10
    assert summary["ratings_count_5"] == 20
    assert summary["ratings_count"] == 40
    (query, params), _kwargs = helpers.fetch_one.await_args
    assert "FILTER (WHERE rating = 1)" in query
    assert "WHERE work_id = %(work_id)s" in query
    assert params == {"work_id": 123}


@pytest.mark.asyncio
async def test_get_work_ratings_summary_none_when_all_counts_zero(helpers):
    # The aggregate always returns one row; an unrated work has all-zero counts.
    helpers.fetch_one.return_value = {f"ratings_count_{i}": 0 for i in range(1, 6)}

    assert await Ratings.get_work_ratings_summary(123) is None


@pytest.mark.asyncio
async def test_get_users_ratings_of_works_uses_any(helpers):
    helpers.fetch_all.return_value = [{"work_id": 1, "rating": 5}, {"work_id": 3, "rating": 2}]

    result = await Ratings.get_users_ratings_of_works("alice", [1, 2, 3])

    assert result == {1: 5, 3: 2}
    (query, params), _kwargs = helpers.fetch_all.await_args
    assert "work_id = ANY(%(work_ids)s)" in query
    assert params == {"username": "alice", "work_ids": [1, 2, 3]}


@pytest.mark.asyncio
async def test_get_users_ratings_of_works_empty_skips_query(helpers):
    assert await Ratings.get_users_ratings_of_works("alice", []) == {}
    helpers.fetch_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_rating(helpers):
    await Ratings.remove("alice", "42")

    helpers.execute.assert_awaited_once_with(
        "DELETE FROM ratings WHERE work_id = %(work_id)s AND username = %(username)s",
        {"work_id": 42, "username": "alice"},
    )


@pytest.mark.asyncio
async def test_add_rating_upserts(helpers, bookshelves):
    await Ratings.add("alice", "42", 5, edition_id=99)

    helpers.execute.assert_awaited_once()
    (query, params), _kwargs = helpers.execute.await_args
    assert "INSERT INTO ratings" in query
    assert "ON CONFLICT (username, work_id) DO UPDATE SET rating = EXCLUDED.rating" in query
    assert params == {"username": "alice", "work_id": 42, "rating": 5, "edition_id": 99}
    # No read-before-write: the upsert alone decides insert vs update.
    helpers.fetch_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("rating", [-1, 6, None, "5"])
async def test_add_rating_invalid_rating(helpers, bookshelves, rating):
    assert await Ratings.add("alice", 42, rating) is None

    helpers.execute.assert_not_awaited()
    bookshelves.read_status.assert_not_called()
    bookshelves.add.assert_not_called()


SUMMARY_ROW = {"books_total": 30, "books_month": 20, "books_week": 10, "raters_total": 3, "raters_month": 2, "raters_week": 1}
EXPECTED_SUMMARY = {
    "total_books_starred": {"total": 30, "month": 20, "week": 10},
    "total_star_raters": {"total": 3, "month": 2, "week": 1},
}


@pytest.mark.asyncio
async def test_summary_is_one_query(helpers):
    helpers.fetch_one.return_value = SUMMARY_ROW

    assert await Ratings.summary() == EXPECTED_SUMMARY
    helpers.fetch_one.assert_awaited_once()
    (query, params), _kwargs = helpers.fetch_one.await_args
    assert "count(DISTINCT username) FILTER (WHERE created >= %(week_ago)s)" in query
    assert params == {"month_ago": DATE_ONE_MONTH_AGO, "week_ago": DATE_ONE_WEEK_AGO}


# --- Sync bridge tests -----------------------------------------------------------


def test_get_work_ratings_summary_sync_bridge(helpers):
    helpers.fetch_one.return_value = {"ratings_count_1": 1, "ratings_count_2": 0, "ratings_count_3": 0, "ratings_count_4": 0, "ratings_count_5": 0}

    summary = Ratings.get_work_ratings_summary_sync(123)

    assert summary is not None
    assert summary["ratings_count"] == 1
    helpers.fetch_one.assert_awaited_once()


def test_summary_sync_bridge(helpers):
    helpers.fetch_one.return_value = SUMMARY_ROW

    assert Ratings.summary_sync() == EXPECTED_SUMMARY


# --- Integration tests (real postgres, marked `integration`) -------------------


@pytest.mark.integration
@pytest.mark.usefixtures("bookshelves")
class TestRatingsIntegration:
    @pytest.mark.asyncio
    async def test_create_update_delete(self, pg_db):
        await Ratings.add("alice", 100, 5, edition_id=1)

        summary = await Ratings.get_work_ratings_summary(100)
        assert summary is not None
        assert summary["ratings_count"] == 1
        assert summary["ratings_count_5"] == 1
        assert await Ratings.get_users_rating_for_work("alice", 100) == 5

        await Ratings.add("alice", 100, 4)
        summary = await Ratings.get_work_ratings_summary(100)
        assert summary is not None
        assert summary["ratings_count"] == 1
        assert summary["ratings_count_4"] == 1
        assert summary["ratings_count_5"] == 0

        await Ratings.remove("alice", 100)
        assert await Ratings.get_work_ratings_summary(100) is None
        assert await Ratings.get_users_rating_for_work("alice", 100) is None

    @pytest.mark.asyncio
    async def test_update_keeps_edition_and_created(self, pg_db):
        await Ratings.add("alice", 100, 5, edition_id=1)
        before = await async_db.fetch_one("SELECT edition_id, created FROM ratings WHERE username = 'alice'")
        assert before is not None

        await Ratings.add("alice", 100, 3, edition_id=2)

        after = await async_db.fetch_one("SELECT rating, edition_id, created FROM ratings WHERE username = 'alice'")
        assert after == {"rating": 3, "edition_id": before["edition_id"], "created": before["created"]}

    @pytest.mark.asyncio
    async def test_concurrent_first_ratings_do_not_conflict(self, pg_db):
        """Regression: SELECT-then-INSERT raced to a primary key violation."""
        results = await asyncio.gather(*(Ratings.add("alice", 300, rating) for rating in [1, 2, 3, 4, 5] * 4), return_exceptions=True)

        assert [r for r in results if isinstance(r, BaseException)] == []
        rows = await Ratings.get_all_works_ratings(300)
        assert len(rows) == 1
        assert rows[0]["rating"] in Ratings.VALID_STAR_RATINGS

    @pytest.mark.asyncio
    async def test_remove_missing_rating_is_noop(self, pg_db):
        await Ratings.remove("alice", 999)
        assert await Ratings.get_all_works_ratings(999) == []

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

        stats = await Ratings.get_rating_stats(200)
        assert stats["num_ratings"] == 3
        assert float(stats["avg_rating"]) == pytest.approx(14 / 3)

    @pytest.mark.asyncio
    async def test_get_users_ratings_of_works(self, pg_db):
        await Ratings.add("alice", 1, 5)
        await Ratings.add("alice", 2, 3)
        await Ratings.add("bob", 3, 4)

        assert await Ratings.get_users_ratings_of_works("alice", [1, 2, 3]) == {1: 5, 2: 3}

    @pytest.mark.asyncio
    async def test_summary_and_most_rated(self, pg_db):
        await Ratings.add("alice", 1, 5)
        await Ratings.add("bob", 1, 4)
        await Ratings.add("alice", 2, 3)
        await Ratings.add("carol", 3, 2)
        # Backdate so each window excludes something: bob's and alice's work 2
        # ratings fall in the month but not the week; carol's in neither.
        for username, work_id, days in [("bob", 1, 10), ("alice", 2, 10), ("carol", 3, 60)]:
            await async_db.execute(
                "UPDATE ratings SET created = %(created)s WHERE username = %(username)s AND work_id = %(work_id)s",
                {"created": datetime.now() - timedelta(days=days), "username": username, "work_id": work_id},
            )

        assert await Ratings.summary() == {
            "total_books_starred": {"total": 4, "month": 3, "week": 1},
            "total_star_raters": {"total": 3, "month": 2, "week": 1},
        }
        assert await Ratings.most_rated_books(limit=1) == [{"work_id": 1, "cnt": 2}]
        assert await Ratings.most_rated_books(since=DATE_ONE_WEEK_AGO) == [{"work_id": 1, "cnt": 1}]
