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
async def test_add_rechecks_domain_conditions_after_concurrent_unique_conflict(helpers):
    helpers.fetch_one.return_value = None
    with (
        patch.object(Bestbook, "_check_award_conditions", new_callable=AsyncMock) as check_conditions,
        pytest.raises(Bestbook.AwardConditionsError, match="already been nominated"),
    ):
        await Bestbook.add("alice", "123", "Fiction")

    assert check_conditions.await_count == 2


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
        assert await Bestbook.get_count(work_id="OL123W") == 1

        with pytest.raises(Bestbook.AwardConditionsError, match="A work may only be nominated one time"):
            await Bestbook.add("alice", "123", "Mystery")
        with pytest.raises(Bestbook.AwardConditionsError, match="Only books which have been marked as read"):
            await Bestbook.add("bob", "123", "Mystery")

        assert await Bestbook.remove("alice", topic="Fiction") == 1
        assert await Bestbook.get_count(username="alice") == 0
