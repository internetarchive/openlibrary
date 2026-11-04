"""Tests for the CommunityEditsQueue model."""

import asyncio
import time
from datetime import UTC, datetime, timedelta

import pytest

from openlibrary.core.async_db import connection, fetch_all, fetch_one, fetch_val
from openlibrary.core.edits import CommunityEditsQueue


@pytest.mark.integration
class TestCommunityEditsQueueIntegration:
    @pytest.mark.asyncio
    async def test_merge_request_create_and_approve(self, pg_db, monkeypatch):
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
        # Approve in a far-from-UTC zone so a local-time `updated` would stand out.
        monkeypatch.setenv("TZ", "Pacific/Kiritimati")  # UTC+14
        time.tzset()
        try:
            assert await CommunityEditsQueue.update_request_status(request_id, CommunityEditsQueue.STATUS["MERGED"], "bob", comment="approved") == 1
        finally:
            monkeypatch.undo()
            time.tzset()

        row = await fetch_one(
            f"SELECT reviewer, status, comments, created, updated FROM {CommunityEditsQueue.TABLENAME} WHERE id = %(id)s",
            {"id": request_id},
        )
        assert row is not None
        assert row["reviewer"] == "bob"
        assert row["status"] == CommunityEditsQueue.STATUS["MERGED"]
        comments = row["comments"]
        assert [comment["message"] for comment in comments["comments"]] == ["created", "approved"]
        assert abs(row["updated"] - datetime.now(UTC).replace(tzinfo=None)) < timedelta(minutes=5)
        assert row["updated"] >= row["created"]

    @pytest.mark.asyncio
    async def test_concurrent_unique_url_submits_insert_once(self, pg_db):
        url = "/authors/merge?records=OL3A,OL4A"
        ids = await asyncio.gather(
            *(CommunityEditsQueue.submit_request(url, "alice", mr_type=CommunityEditsQueue.TYPE["AUTHOR_MERGE"], unique_url=True) for _ in range(10))
        )

        assert len([request_id for request_id in ids if request_id]) == 1
        assert await fetch_val(f"SELECT count(*) FROM {CommunityEditsQueue.TABLENAME} WHERE url = %(url)s", {"url": url}) == 1

    @pytest.mark.asyncio
    async def test_update_submitter_name_and_dry_run(self, pg_db):
        submitter = "@anonymize-test"
        new_submitter = "@anonymous-test"
        bystander = "@bystander"
        async with connection() as conn:
            for name in (submitter, bystander):
                await conn.execute(
                    "INSERT INTO community_edits_queue (title, submitter, url) VALUES ('test', %s, '/test')",
                    (name,),
                )

        assert await CommunityEditsQueue.update_submitter_name(submitter, new_submitter, _test=True) == 1
        assert await fetch_all("SELECT 1 FROM community_edits_queue WHERE submitter = %(submitter)s", {"submitter": submitter})
        assert await CommunityEditsQueue.update_submitter_name(submitter, new_submitter) == 1
        assert len(await fetch_all("SELECT 1 FROM community_edits_queue WHERE submitter = %(submitter)s", {"submitter": new_submitter})) == 1
        assert len(await fetch_all("SELECT 1 FROM community_edits_queue WHERE submitter = %(submitter)s", {"submitter": bystander})) == 1
