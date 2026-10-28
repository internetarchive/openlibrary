"""Tests for the CommunityEditsQueue model."""

from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core.async_db import fetch_one
from openlibrary.core.edits import CommunityEditsQueue


@pytest.mark.asyncio
async def test_exists_uses_parameterized_url():
    with patch("openlibrary.core.edits.fetch_one", new_callable=AsyncMock, return_value={"request_exists": True}) as fetch_one:
        assert await CommunityEditsQueue.exists("/authors/merge?records=OL1A,OL2A")

    query, params = fetch_one.await_args.args
    assert "url = %(url)s" in query
    assert params == {"url": "/authors/merge?records=OL1A,OL2A"}


@pytest.mark.asyncio
async def test_submit_request_returns_inserted_id():
    with patch("openlibrary.core.edits.fetch_one", new_callable=AsyncMock, return_value={"id": 42}) as fetch_one:
        request_id = await CommunityEditsQueue.submit_request(
            "/authors/merge?records=OL1A,OL2A",
            "alice",
            reviewer="alice",
            status=CommunityEditsQueue.STATUS["MERGED"],
            title="Author",
            comment="merged",
            mr_type=CommunityEditsQueue.TYPE["AUTHOR_MERGE"],
        )

    assert request_id == 42
    query, params = fetch_one.await_args.args
    assert "RETURNING id" in query
    assert params["submitter"] == "alice"
    assert params["reviewer"] == "alice"
    assert params["mr_type"] == CommunityEditsQueue.TYPE["AUTHOR_MERGE"]
    assert params["comments"].obj["comments"][0]["username"] == "alice"
    assert params["comments"].obj["comments"][0]["message"] == "merged"


@pytest.mark.integration
class TestCommunityEditsQueueIntegration:
    @pytest.mark.asyncio
    async def test_merge_request_create_and_approve(self, pg_db):
        url = "/authors/merge?records=OL1A,OL2A"
        assert not await CommunityEditsQueue.exists(url)

        request_id = await CommunityEditsQueue.submit_request(
            url,
            "alice",
            reviewer="alice",
            status=CommunityEditsQueue.STATUS["MERGED"],
            title="Author",
            comment="created",
            mr_type=CommunityEditsQueue.TYPE["AUTHOR_MERGE"],
        )

        assert request_id is not None
        assert await CommunityEditsQueue.exists(url)
        assert (
            await CommunityEditsQueue.update_request_status(
                request_id,
                CommunityEditsQueue.STATUS["MERGED"],
                "bob",
                comment="approved",
            )
            == 1
        )

        row = await fetch_one(
            f"SELECT reviewer, status, comments FROM {CommunityEditsQueue.TABLENAME} WHERE id = %(id)s",
            {"id": request_id},
        )
        assert row["reviewer"] == "bob"
        assert row["status"] == CommunityEditsQueue.STATUS["MERGED"]
        comments = row["comments"]
        assert [comment["message"] for comment in comments["comments"]] == ["created", "approved"]
