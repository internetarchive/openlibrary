"""Tests for the async follows model and its PostgreSQL queries."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from openlibrary.core import async_db
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

    @pytest.mark.parametrize("disabled", [False, True])
    @pytest.mark.asyncio
    async def test_subscribe_does_not_change_existing_subscription(self, pg_db, disabled):
        created = datetime(2000, 1, 1)
        updated = datetime(2001, 1, 1)
        await async_db.execute(
            "INSERT INTO follows (subscriber, publisher, disabled, created, updated) "
            "VALUES (%(subscriber)s, %(publisher)s, %(disabled)s, %(created)s, %(updated)s)",
            {"subscriber": "alice", "publisher": "bob", "disabled": disabled, "created": created, "updated": updated},
        )
        before = await async_db.fetch_one(
            "SELECT subscriber, publisher, disabled, created, updated FROM follows WHERE subscriber = %(subscriber)s AND publisher = %(publisher)s",
            {"subscriber": "alice", "publisher": "bob"},
        )

        await PubSub.subscribe("alice", "bob")
        await PubSub.subscribe("alice", "bob")

        after = await async_db.fetch_one(
            "SELECT subscriber, publisher, disabled, created, updated FROM follows WHERE subscriber = %(subscriber)s AND publisher = %(publisher)s",
            {"subscriber": "alice", "publisher": "bob"},
        )
        assert after == before

    @pytest.mark.asyncio
    async def test_subscribe_only_changes_the_requested_pair(self, pg_db):
        pairs = [("alice", "bob"), ("alice", "carol"), ("dave", "bob")]
        for subscriber, publisher in pairs:
            await PubSub.subscribe(subscriber, publisher)

        await PubSub.subscribe("alice", "bob")

        rows = await async_db.fetch_all("SELECT subscriber, publisher FROM follows ORDER BY subscriber, publisher")
        assert {(row["subscriber"], row["publisher"]) for row in rows} == set(pairs)

    @pytest.mark.asyncio
    async def test_subscribe_binds_names_as_parameters(self, pg_db):
        subscriber, publisher = "reader'नया", "author'quoted"

        await PubSub.subscribe(subscriber, publisher)
        await PubSub.subscribe(subscriber, publisher)

        rows = await async_db.fetch_all(
            "SELECT subscriber, publisher FROM follows WHERE subscriber = %(subscriber)s AND publisher = %(publisher)s",
            {"subscriber": subscriber, "publisher": publisher},
        )
        assert len(rows) == 1
        assert (rows[0]["subscriber"], rows[0]["publisher"]) == (subscriber, publisher)

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

    @pytest.mark.asyncio
    async def test_following_and_followers_paginate(self, pg_db):
        for publisher in ("bob", "carol", "dave"):
            await PubSub.subscribe("alice", publisher)
        for subscriber in ("erin", "frank", "grace"):
            await PubSub.subscribe(subscriber, "zed")

        assert len(await PubSub.get_following("alice", limit=2)) == 2
        assert len(await PubSub.get_following("alice", limit=2, offset=2)) == 1
        assert len(await PubSub.get_followers("zed", limit=2)) == 2
        assert len(await PubSub.get_followers("zed", limit=2, offset=2)) == 1

    @pytest.mark.asyncio
    async def test_feed_reads_books_of_enabled_publishers(self, pg_db):
        await PubSub.subscribe("alice", "bob")
        await PubSub.subscribe("alice", "carol")
        await PubSub.subscribe("alice", "dave")
        await PubSub.toggle_privacy("dave", private=True)
        for username, work_id, created in [
            ("bob", 1, datetime(2020, 1, 1)),
            ("carol", 2, datetime(2021, 1, 1)),
            ("dave", 3, datetime(2022, 1, 1)),
            ("erin", 4, datetime(2023, 1, 1)),
        ]:
            await async_db.execute(
                "INSERT INTO bookshelves_books (username, work_id, bookshelf_id, created) VALUES (%(username)s, %(work_id)s, 1, %(created)s)",
                {"username": username, "work_id": work_id, "created": created},
            )

        with patch.object(Bookshelves, "add_solr_works_async", new_callable=AsyncMock):
            feed = await PubSub.get_feed("alice")
            assert [(row.username, row.key) for row in feed] == [("carol", "/works/OL2W"), ("bob", "/works/OL1W")]
            assert [row.username for row in await PubSub.get_feed("alice", limit=1, offset=1)] == ["bob"]
            assert await PubSub.get_feed("nobody") == []
