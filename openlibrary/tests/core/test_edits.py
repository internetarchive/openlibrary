"""Tests for the community edits queue model."""

import pytest

from openlibrary.core.async_db import connection, fetch_all
from openlibrary.core.edits import CommunityEditsQueue


@pytest.mark.integration
class TestCommunityEditsQueueAsync:
    @pytest.mark.asyncio
    async def test_update_submitter_name_and_dry_run(self, pg_db):
        submitter = "@anonymize-test"
        new_submitter = "@anonymous-test"
        async with connection() as conn:
            await conn.execute(
                "INSERT INTO community_edits_queue (title, submitter, url) VALUES ('test', %s, '/test')",
                (submitter,),
            )

        assert await CommunityEditsQueue.update_submitter_name(submitter, new_submitter, _test=True) == 1
        assert await fetch_all("SELECT 1 FROM community_edits_queue WHERE submitter = %(submitter)s", {"submitter": submitter})
        assert await CommunityEditsQueue.update_submitter_name(submitter, new_submitter) == 1
        assert await fetch_all("SELECT 1 FROM community_edits_queue WHERE submitter = %(submitter)s", {"submitter": new_submitter})
