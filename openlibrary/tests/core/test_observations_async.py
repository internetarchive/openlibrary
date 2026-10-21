"""Unit and integration tests for async observation queries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core import async_db
from openlibrary.core.observations import Observations, get_observation_metrics


@pytest.fixture
def helpers():
    with (
        patch("openlibrary.core.observations.fetch_all", new_callable=AsyncMock) as fetch_all,
        patch("openlibrary.core.observations.fetch_val", new_callable=AsyncMock) as fetch_val,
    ):
        yield SimpleNamespace(fetch_all=fetch_all, fetch_val=fetch_val)


@pytest.mark.asyncio
async def test_total_unique_respondents(helpers):
    helpers.fetch_val.return_value = 2

    total = await Observations.total_unique_respondents(work_id=123, since=None)

    assert total == 2
    (query, params), _kwargs = helpers.fetch_val.await_args
    assert query == "SELECT COUNT(DISTINCT(username)) FROM observations WHERE work_id = %(work_id)s"
    assert params == {"work_id": 123, "since": None}


@pytest.mark.asyncio
async def test_count_unique_respondents_by_type(helpers):
    helpers.fetch_all.return_value = [{"type": 1, "total_respondents": 2}]

    result = await Observations.count_unique_respondents_by_type(123)

    assert result == {1: 2}
    (query, params), _kwargs = helpers.fetch_all.await_args
    assert "count(distinct(username)) AS total_respondents" in query
    assert "WHERE work_id = %(work_id)s" in query
    assert params == {"work_id": 123}


@pytest.mark.asyncio
async def test_count_observations(helpers):
    rows = [{"type_id": 1, "value_id": 4, "total": 2}]
    helpers.fetch_all.return_value = rows

    assert await Observations.count_observations(123) == rows
    (query, params), _kwargs = helpers.fetch_all.await_args
    assert "GROUP BY type_id, value_id" in query
    assert "ORDER BY type_id, total DESC" in query
    assert params == {"work_id": 123}


@pytest.mark.asyncio
async def test_observation_metrics_await_async_aggregates():
    with (
        patch.object(Observations, "total_unique_respondents", new_callable=AsyncMock, return_value=1) as total,
        patch.object(Observations, "count_unique_respondents_by_type", new_callable=AsyncMock, return_value={1: 1}) as by_type,
        patch.object(
            Observations,
            "count_observations",
            new_callable=AsyncMock,
            return_value=[{"type_id": 1, "value_id": 4, "total": 1}],
        ) as counts,
    ):
        metrics = await get_observation_metrics("/works/OL123W")

    assert metrics["work_id"] == "123"
    assert metrics["total_respondents"] == 1
    assert metrics["observations"][0]["values"] == [{"value": "Slow paced", "count": 1}]
    total.assert_awaited_once_with(123)
    by_type.assert_awaited_once_with(123)
    counts.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_observation_metrics_skip_aggregate_queries_without_respondents():
    with (
        patch.object(Observations, "total_unique_respondents", new_callable=AsyncMock, return_value=0) as total,
        patch.object(Observations, "count_unique_respondents_by_type", new_callable=AsyncMock) as by_type,
        patch.object(Observations, "count_observations", new_callable=AsyncMock) as counts,
    ):
        metrics = await get_observation_metrics("/works/OL123W")

    assert metrics == {"work_id": "123", "total_respondents": 0, "observations": []}
    total.assert_awaited_once_with(123)
    by_type.assert_not_awaited()
    counts.assert_not_awaited()


def test_sync_bridges_call_async_methods():
    def run_coroutine(coro):
        coro.close()
        return 3

    with patch("openlibrary.core.observations.async_bridge.run", side_effect=run_coroutine) as run:
        assert Observations.total_unique_respondents_sync(123, None) == 3
        run.assert_called_once()


@pytest.mark.integration
class TestObservationMetricsIntegration:
    @pytest.mark.asyncio
    async def test_metrics_aggregate_rows(self, pg_db):
        async with async_db.connection() as conn:
            await conn.execute(
                "INSERT INTO observations (work_id, username, observation_type, observation_value) "
                "VALUES (123, 'alice', 1, 4), (123, 'bob', 1, 4), (123, 'bob', 2, 7)"
            )

        metrics = await get_observation_metrics("/works/OL123W")

        assert metrics["total_respondents"] == 2
        assert [item["label"] for item in metrics["observations"]] == ["Pace", "Enjoyability"]
        assert metrics["observations"][0]["total_respondents_for_type"] == 2
        assert metrics["observations"][0]["values"] == [{"value": "Slow paced", "count": 2}]
        assert metrics["observations"][1]["values"] == [{"value": "Engaging", "count": 1}]
