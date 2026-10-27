"""Unit and integration tests for async bestbook queries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core import async_db
from openlibrary.core.bestbook import Bestbook


@pytest.fixture
def helpers():
    with (
        patch("openlibrary.core.bestbook.fetch_all", new_callable=AsyncMock) as fetch_all,
        patch("openlibrary.core.bestbook.fetch_one", new_callable=AsyncMock) as fetch_one,
        patch("openlibrary.core.bestbook.fetch_val", new_callable=AsyncMock) as fetch_val,
    ):
        yield SimpleNamespace(fetch_all=fetch_all, fetch_one=fetch_one, fetch_val=fetch_val)


@pytest.mark.asyncio
async def test_get_awards_builds_parameterized_filters(helpers):
    helpers.fetch_all.return_value = [{"award_id": 1, "username": "alice", "work_id": 123, "topic": "Fiction"}]

    awards = await Bestbook.get_awards(work_id="123", username="alice", topic="Fiction")

    assert awards == helpers.fetch_all.return_value
    (query, params), _kwargs = helpers.fetch_all.await_args
    assert "WHERE work_id = %(work_id)s AND username = %(username)s AND topic = %(topic)s" in query
    assert params == {"work_id": 123, "username": "alice", "topic": "Fiction"}


@pytest.mark.asyncio
async def test_get_count_uses_fetch_val(helpers):
    helpers.fetch_val.return_value = 2

    assert await Bestbook.get_count(username="alice", topic="Fiction") == 2

    (query, params), _kwargs = helpers.fetch_val.await_args
    assert query == "SELECT count(*) FROM bestbooks WHERE username = %(username)s AND topic = %(topic)s"
    assert params == {"username": "alice", "topic": "Fiction"}


@pytest.mark.asyncio
async def test_get_count_accepts_work_olid(helpers):
    helpers.fetch_val.return_value = 1

    assert await Bestbook.get_count(work_id="OL123W") == 1

    _, params = helpers.fetch_val.await_args.args
    assert params == {"work_id": 123}


def test_sync_bridges_preserve_legacy_callers():
    results = iter([[{"award_id": 1, "work_id": 123, "topic": "Fiction"}], 5])

    def run_coroutine(coroutine):
        coroutine.close()
        return next(results)

    with patch("openlibrary.core.bestbook.async_bridge.run", side_effect=run_coroutine) as run:
        awards = Bestbook.get_awards_sync(work_id="123")
        count = Bestbook.get_count_sync(work_id="123")

    assert awards[0].work_id == 123
    assert count == 5
    assert run.call_count == 2


@pytest.mark.asyncio
async def test_add_validates_then_inserts_with_returning(helpers):
    helpers.fetch_one.return_value = {"award_id": 42}
    with (
        patch.object(Bestbook, "_check_award_conditions", new_callable=AsyncMock) as check_conditions,
    ):
        result = await Bestbook.add("alice", "123", "Fiction", "Great book", edition_id=456)

    assert result == 42
    check_conditions.assert_awaited_once_with("alice", "123", "Fiction")
    (query, params), _kwargs = helpers.fetch_one.await_args
    assert "ON CONFLICT DO NOTHING" in query
    assert "RETURNING award_id" in query
    assert params == {
        "username": "alice",
        "work_id": "123",
        "edition_id": 456,
        "topic": "Fiction",
        "comment": "Great book",
    }


@pytest.mark.asyncio
async def test_add_rechecks_domain_conditions_after_concurrent_unique_conflict(helpers):
    helpers.fetch_one.return_value = None
    with (
        patch.object(Bestbook, "_check_award_conditions", new_callable=AsyncMock) as check_conditions,
        pytest.raises(Bestbook.AwardConditionsError, match="already been nominated"),
    ):
        await Bestbook.add("alice", "123", "Fiction")

    assert check_conditions.await_count == 2


@pytest.mark.asyncio
async def test_remove_returns_deleted_row_count(helpers):
    helpers.fetch_all.return_value = [{"award_id": 1}, {"award_id": 2}]

    assert await Bestbook.remove("alice", work_id="123", topic="Fiction") == 2

    (query, params), _kwargs = helpers.fetch_all.await_args
    assert "username = %(username)s AND (work_id = %(work_id)s OR topic = %(topic)s)" in query
    assert "RETURNING award_id" in query
    assert params == {"username": "alice", "work_id": "123", "topic": "Fiction"}


@pytest.mark.asyncio
async def test_remove_requires_a_filter():
    with pytest.raises(ValueError, match="Either work_id or topic must be specified"):
        await Bestbook.remove("alice")


@pytest.mark.integration
class TestBestbookIntegration:
    @pytest.mark.asyncio
    async def test_award_validation_queries_and_mutations(self, pg_db):
        await async_db.execute("INSERT INTO bookshelves_books (username, work_id, bookshelf_id) VALUES ('alice', 123, 3)")

        award_id = await Bestbook.add("alice", "123", "Fiction", "A favorite")

        assert award_id is not None
        awards = await Bestbook.get_awards(username="alice", work_id="123")
        assert len(awards) == 1
        assert awards[0]["topic"] == "Fiction"
        assert await Bestbook.get_count(username="alice") == 1
        assert await Bestbook.get_count(work_id="123", topic="Fiction") == 1

        with pytest.raises(Bestbook.AwardConditionsError, match="A work may only be nominated one time"):
            await Bestbook.add("alice", "123", "Mystery")
        with pytest.raises(Bestbook.AwardConditionsError, match="Only books which have been marked as read"):
            await Bestbook.add("bob", "123", "Mystery")

        assert await Bestbook.remove("alice", topic="Fiction") == 1
        assert await Bestbook.get_count(username="alice") == 0
