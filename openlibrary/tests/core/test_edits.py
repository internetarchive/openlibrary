"""Tests for the community edits queue model."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from psycopg.errors import UniqueViolation

from openlibrary.core.async_db import connection, fetch_all
from openlibrary.core.edits import CommunityEditsQueue


@pytest.fixture
def mocked_async_connection(monkeypatch):
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=SimpleNamespace(rowcount=2))
    conn.rollback = AsyncMock()

    @asynccontextmanager
    async def connection():
        yield conn

    monkeypatch.setattr("openlibrary.core.edits.connection", connection)
    return conn


@pytest.mark.asyncio
async def test_update_submitter_name_uses_async_connection_and_rolls_back_for_test_mode(mocked_async_connection):
    rows_changed = await CommunityEditsQueue.update_submitter_name("alice", "anonymous-alice", _test=True)

    assert rows_changed == 2
    query, params = mocked_async_connection.execute.await_args.args
    assert query == "UPDATE community_edits_queue SET submitter = %(new_username)s WHERE submitter = %(submitter)s"
    assert params == {"submitter": "alice", "new_username": "anonymous-alice"}
    mocked_async_connection.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_submitter_name_unique_conflict_rolls_back_and_returns_zero(mocked_async_connection):
    mocked_async_connection.execute.side_effect = UniqueViolation("duplicate submitter")

    rows_changed = await CommunityEditsQueue.update_submitter_name("alice", "anonymous-alice")

    assert rows_changed == 0
    mocked_async_connection.rollback.assert_awaited_once()


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
