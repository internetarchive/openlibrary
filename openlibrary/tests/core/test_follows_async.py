"""Tests for the async follows model and its PostgreSQL queries."""

from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.follows import PubSub


@pytest.mark.asyncio
async def test_subscribe_uses_conflict_safe_insert():
    with patch("openlibrary.core.follows.execute", new_callable=AsyncMock) as execute:
        await PubSub.subscribe("alice", "bob")

    query, params = execute.await_args.args
    assert "ON CONFLICT (subscriber, publisher) DO NOTHING" in query
    assert params == {"subscriber": "alice", "publisher": "bob"}


@pytest.mark.asyncio
async def test_unsubscribe_uses_async_execute():
    with patch("openlibrary.core.follows.execute", new_callable=AsyncMock) as execute:
        await PubSub.unsubscribe("alice", "bob")

    assert "DELETE FROM follows" in execute.await_args.args[0]
    assert execute.await_args.args[1] == {"subscriber": "alice", "publisher": "bob"}


@pytest.mark.asyncio
async def test_toggle_privacy_only_updates_disabled():
    with patch("openlibrary.core.follows.execute", new_callable=AsyncMock) as execute:
        await PubSub.toggle_privacy("bob", private=True)

    query, params = execute.await_args.args
    assert "SET disabled = %(disabled)s WHERE" in query
    assert "updated =" not in query
    assert params == {"disabled": True, "publisher": "bob"}


@pytest.mark.asyncio
async def test_get_followers_returns_attribute_accessible_rows():
    row = {"subscriber": "alice", "publisher": "bob", "disabled": False}
    with patch("openlibrary.core.follows.fetch_all", new_callable=AsyncMock, return_value=[row]):
        followers = await PubSub.get_followers("bob")

    assert followers[0].subscriber == "alice"


@pytest.mark.asyncio
async def test_feed_uses_async_solr_enrichment():
    feed_row = {"username": "bob", "work_id": 42, "bookshelf_id": 1}
    with (
        patch.object(PubSub, "get_following", new_callable=AsyncMock, return_value=[{"publisher": "bob"}]),
        patch("openlibrary.core.follows.fetch_all", new_callable=AsyncMock, return_value=[feed_row]),
        patch.object(Bookshelves, "add_solr_works_async", new_callable=AsyncMock) as add_solr_works_async,
    ):
        result = await PubSub.get_feed("alice")

    assert result == [{**feed_row, "key": "/works/OL42W"}]
    assert result[0].key == "/works/OL42W"
    add_solr_works_async.assert_awaited_once_with(result)


@pytest.mark.integration
class TestPubSubIntegration:
    @pytest.mark.asyncio
    async def test_subscribe_is_idempotent_and_unsubscribe_removes_subscription(self, pg_db):
        await PubSub.subscribe("alice", "bob")
        await PubSub.subscribe("alice", "bob")
        assert await PubSub.is_subscribed("alice", "bob") is True
        await PubSub.unsubscribe("alice", "bob")
        assert await PubSub.is_subscribed("alice", "bob") is False

    @pytest.mark.asyncio
    async def test_toggle_privacy_updates_disabled_state(self, pg_db):
        await PubSub.subscribe("alice", "bob")
        await PubSub.toggle_privacy("bob", private=True)
        follows = await PubSub.get_following("alice")
        assert follows[0]["disabled"] is True

    @pytest.mark.asyncio
    async def test_follow_queries(self, pg_db):
        await PubSub.subscribe("alice", "bob")
        await PubSub.subscribe("alice", "carol")
        await PubSub.subscribe("dave", "bob")
        await PubSub.toggle_privacy("bob", private=True)

        assert {follow["subscriber"] for follow in await PubSub.get_followers("bob")} == {"alice", "dave"}
        assert {follow["publisher"] for follow in await PubSub.get_following("alice")} == {"bob", "carol"}
        assert {follow["publisher"] for follow in await PubSub.get_following("alice", exclude_disabled=True)} == {"carol"}
        assert await PubSub.is_subscribed("alice", "bob") is True
        assert await PubSub.is_subscribed("nobody", "bob") is False
        assert await PubSub.count_following("alice") == 2
        assert await PubSub.count_followers("bob") == 2
        assert await PubSub.is_following("alice") is True
        assert await PubSub.is_following("nobody") is False
        assert (await PubSub.summary())["total_following_count"] == {"total": 2, "month": 2, "week": 2}
