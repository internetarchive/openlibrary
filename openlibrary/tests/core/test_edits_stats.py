import datetime as dt
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from openlibrary.core.async_db import close_pool, execute
from openlibrary.core.edits import CommunityEditsQueue

DECLINED, PENDING, MERGED = 0, 1, 2
WORK, AUTHOR = 1, 2


def row(submitter, reviewer, status, mr_type=WORK, updated="2024-01-01 00:00:00"):
    return {
        "title": "t",
        "submitter": submitter,
        "reviewer": reviewer,
        "url": f"/merge/{submitter}/{reviewer}/{status}/{mr_type}/{updated}",
        "mr_type": mr_type,
        "status": status,
        "updated": updated,
    }


ROWS = [
    row("alice", "rita", MERGED, WORK),
    row("alice", "rita", MERGED, AUTHOR),
    row("alice", "rita", DECLINED, WORK),
    row("bob", "rita", DECLINED, WORK),
    row("bob", "sam", MERGED, WORK),
    row("bob", None, PENDING),
    row("carol", "sam", PENDING),
    row("carol", "sam", MERGED, WORK, updated="2023-01-01 00:00:00"),
]


@pytest_asyncio.fixture
async def stats_db(pg_db):
    try:
        for values in ROWS:
            await execute(
                "INSERT INTO community_edits_queue (title, submitter, reviewer, url, mr_type, status, updated) "
                "VALUES (%(title)s, %(submitter)s, %(reviewer)s, %(url)s, %(mr_type)s, %(status)s, %(updated)s)",
                values,
            )
        yield
    finally:
        await close_pool()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.usefixtures("stats_db")
class TestCommunityEditsQueueStatsIntegration:
    async def test_reviewer_counts(self):
        stats = {r["username"]: r for r in await CommunityEditsQueue.get_stats("reviewer")}
        assert set(stats) == {"rita", "sam"}
        assert stats["rita"] == {
            "username": "rita",
            "total": 4,
            "merged": 2,
            "declined": 2,
            "author_requests": 1,
            "work_requests": 3,
            "merge_rate": 50.0,
        }
        assert stats["sam"]["total"] == 2
        assert stats["sam"]["merged"] == 2

    async def test_pending_requests_are_not_counted(self):
        submitters = {r["username"]: r for r in await CommunityEditsQueue.get_stats("submitter")}
        assert submitters["bob"]["total"] == 2
        assert submitters["carol"]["total"] == 1

    async def test_submitter_merge_rate(self):
        submitters = {r["username"]: r for r in await CommunityEditsQueue.get_stats("submitter")}
        assert submitters["alice"]["merge_rate"] == pytest.approx(66.666, abs=0.01)
        assert submitters["bob"]["merge_rate"] == 50.0

    async def test_unassigned_requests_have_no_reviewer_row(self):
        assert None not in {r["username"] for r in await CommunityEditsQueue.get_stats("reviewer")}

    async def test_since_limits_to_recent_requests(self):
        since = dt.date(2023, 6, 1)
        assert {r["username"] for r in await CommunityEditsQueue.get_stats("submitter", since=since)} == {"alice", "bob"}
        assert await CommunityEditsQueue.get_stats_count("submitter", since=since) == 2
        assert await CommunityEditsQueue.get_stats_count("submitter") == 3

    async def test_sort_and_order(self):
        by_total = [r["username"] for r in await CommunityEditsQueue.get_stats("submitter", sort="total")]
        assert by_total == ["alice", "bob", "carol"]
        ascending = [r["username"] for r in await CommunityEditsQueue.get_stats("submitter", sort="total", order="asc")]
        assert ascending == ["carol", "bob", "alice"]
        by_rate = [r["username"] for r in await CommunityEditsQueue.get_stats("submitter", sort="rate")]
        assert by_rate[0] == "carol"

    async def test_pagination(self):
        page_1 = await CommunityEditsQueue.get_stats("submitter", limit=2, page=1)
        page_2 = await CommunityEditsQueue.get_stats("submitter", limit=2, page=2)
        assert [r["username"] for r in page_1] == ["alice", "bob"]
        assert [r["username"] for r in page_2] == ["carol"]

    async def test_unknown_role_is_rejected(self):
        with pytest.raises(ValueError, match="Unknown stats role"):
            await CommunityEditsQueue.get_stats("submitter; DROP TABLE x")
        with pytest.raises(ValueError, match="Unknown stats role"):
            await CommunityEditsQueue.get_stats_count("status")

    async def test_unknown_sort_is_rejected(self):
        with pytest.raises(ValueError, match="Unknown stats sort"):
            await CommunityEditsQueue.get_stats("submitter", sort="total; DROP TABLE x")

    @pytest.mark.parametrize("page", [0, -3])
    async def test_nonpositive_page_is_clamped(self, page):
        expected = await CommunityEditsQueue.get_stats("submitter", limit=2, page=1)
        assert await CommunityEditsQueue.get_stats("submitter", limit=2, page=page) == expected


@pytest.mark.asyncio
async def test_stats_use_async_helpers(monkeypatch):
    rows = AsyncMock(
        return_value=[
            {
                "username": "alice",
                "total": 3,
                "merged": 2,
                "declined": 1,
                "author_requests": 1,
                "work_requests": 2,
                "merge_rate": 66.666,
            }
        ]
    )
    count = AsyncMock(return_value=1)
    monkeypatch.setattr("openlibrary.core.edits.fetch_all", rows)
    monkeypatch.setattr("openlibrary.core.edits.fetch_val", count)
    since = dt.date(2026, 1, 1)
    result = await CommunityEditsQueue.get_stats("submitter", since=since, sort="rate", order="asc", limit=10, page=2)
    assert result[0]["username"] == "alice"
    query, params = rows.await_args.args
    assert "updated >= %(since)s" in query
    assert "LIMIT %(limit)s OFFSET %(offset)s" in query
    assert "ORDER BY merge_rate ASC, username ASC" in query
    assert params == {"since": "2026-01-01", "limit": 10, "offset": 10}
    assert await CommunityEditsQueue.get_stats_count("submitter", since=since) == 1
    query, params = count.await_args.args
    assert "count(DISTINCT submitter)" in query
    assert params == {"since": "2026-01-01"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("get_stats", {"role": "submitter; DROP TABLE x"}),
        ("get_stats_count", {"role": "status"}),
        ("get_stats", {"role": "reviewer", "sort": "total; DROP TABLE x"}),
    ],
)
async def test_invalid_stats_choices_never_query(monkeypatch, method, args):
    query = AsyncMock()
    monkeypatch.setattr("openlibrary.core.edits.fetch_all", query)
    monkeypatch.setattr("openlibrary.core.edits.fetch_val", query)
    with pytest.raises(ValueError, match="Unknown stats"):
        await getattr(CommunityEditsQueue, method)(**args)
    query.assert_not_awaited()
