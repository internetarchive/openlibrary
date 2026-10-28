"""Unit and integration tests for the observations model."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core import async_db
from openlibrary.core.observations import Observations, _sort_values, get_observation_metrics
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO


def test_sort_values():
    orders_list = [3, 4, 2, 1]
    values_list = [
        {"id": 1, "name": "order"},
        {"id": 2, "name": "in"},
        {"id": 3, "name": "this"},
        {"id": 4, "name": "is"},
    ]

    # sorted values returned given unsorted list
    assert _sort_values(orders_list, values_list) == ["this", "is", "in", "order"]

    # no errors thrown when orders list contains an ID not found in the values list
    orders_list.insert(0, 5)
    assert _sort_values(orders_list, values_list) == ["this", "is", "in", "order"]

    # value with ID that is not in orders list will not be included in sorted list
    values_list.append({"id": 100, "name": "impossible!"})
    assert _sort_values(orders_list, values_list) == ["this", "is", "in", "order"]


@pytest.fixture
def helpers():
    with (
        patch("openlibrary.core.observations.fetch_all", new_callable=AsyncMock) as fetch_all,
        patch("openlibrary.core.observations.fetch_one", new_callable=AsyncMock) as fetch_one,
        patch("openlibrary.core.observations.fetch_val", new_callable=AsyncMock) as fetch_val,
    ):
        yield SimpleNamespace(fetch_all=fetch_all, fetch_one=fetch_one, fetch_val=fetch_val)


@pytest.mark.asyncio
async def test_total_unique_respondents_filters_zero_work_id(helpers):
    await Observations.total_unique_respondents(work_id=0)

    (query, params), _kwargs = helpers.fetch_val.await_args
    assert "WHERE work_id = %(work_id)s" in query
    assert params == {"work_id": 0}


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


SUMMARY_ROW = {
    "reviews_total": 30,
    "reviews_month": 20,
    "reviews_week": 10,
    "books_total": 12,
    "books_month": 8,
    "books_week": 4,
    "reviewers_total": 7,
    "reviewers_month": 5,
    "reviewers_week": 3,
}


@pytest.mark.asyncio
async def test_summary_uses_one_aggregate_query(helpers):
    helpers.fetch_one.return_value = SUMMARY_ROW

    assert await Observations.summary() == {
        "total_reviews": {"total": 30, "month": 20, "week": 10},
        "total_books_reviewed": {"total": 12, "month": 8, "week": 4},
        "total_reviewers": {"total": 7, "month": 5, "week": 3},
    }
    helpers.fetch_one.assert_awaited_once()
    (query, params), _kwargs = helpers.fetch_one.await_args
    assert "count(*) FILTER (WHERE created >= %(month_ago)s)" in query
    assert "count(DISTINCT work_id) FILTER (WHERE created >= %(week_ago)s)" in query
    assert "count(DISTINCT username) FILTER (WHERE created >= %(week_ago)s)" in query
    assert params == {"month_ago": DATE_ONE_MONTH_AGO, "week_ago": DATE_ONE_WEEK_AGO}


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

    @pytest.mark.asyncio
    async def test_summary_aggregate_rows(self, pg_db):
        async with async_db.connection() as conn:
            await conn.execute(
                "INSERT INTO observations (work_id, username, observation_type, observation_value, created) "
                "VALUES (123, 'alice', 1, 4, now()), (123, 'bob', 1, 4, now()), "
                "(456, 'bob', 2, 7, now()), (789, 'carol', 1, 5, now() - interval '2 months')"
            )

        summary = await Observations.summary()

        assert summary["total_reviews"] == {"total": 4, "month": 3, "week": 3}
        assert summary["total_books_reviewed"] == {"total": 3, "month": 2, "week": 2}
        assert summary["total_reviewers"] == {"total": 3, "month": 2, "week": 2}
