import logging
from datetime import datetime
from typing import TypedDict

import web

from openlibrary.core.async_db import execute, fetch_all, fetch_one
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

logger = logging.getLogger(__name__)


class Follow(TypedDict):
    """A row from the ``follows`` table."""

    subscriber: str
    publisher: str
    disabled: bool
    created: datetime | None
    updated: datetime | None


class PubSub:
    TABLENAME = "follows"
    PRIMARY_KEY = ("subscriber", "publisher")

    @classmethod
    async def subscribe(cls, subscriber: str, publisher: str) -> None:
        """Create a subscription if it doesn't exist.
        Uses ON CONFLICT DO NOTHING to avoid race conditions.
        """
        await execute(
            f"INSERT INTO {cls.TABLENAME} (subscriber, publisher, disabled) "
            "VALUES (%(subscriber)s, %(publisher)s, false) "
            "ON CONFLICT (subscriber, publisher) DO NOTHING",
            {"subscriber": subscriber, "publisher": publisher},
        )

    @classmethod
    def subscribe_sync(cls, subscriber: str, publisher: str) -> None:
        async_bridge.run(cls.subscribe(subscriber, publisher))

    @classmethod
    async def unsubscribe(cls, subscriber: str, publisher: str) -> None:
        """Remove a subscription."""
        await execute(
            f"DELETE FROM {cls.TABLENAME} WHERE subscriber = %(subscriber)s AND publisher = %(publisher)s",
            {"subscriber": subscriber, "publisher": publisher},
        )

    @classmethod
    async def is_subscribed(cls, subscriber: str, publisher: str) -> bool:
        """Check if a subscription exists."""
        query = f"SELECT 1 FROM {cls.TABLENAME} WHERE subscriber = %(subscriber)s AND publisher = %(publisher)s LIMIT 1"
        row = await fetch_one(query, {"subscriber": subscriber, "publisher": publisher})
        return row is not None

    @classmethod
    def is_subscribed_sync(cls, subscriber: str, publisher: str) -> bool:
        return async_bridge.run(cls.is_subscribed(subscriber, publisher))

    @classmethod
    async def get_followers(cls, publisher: str, limit: int | None = None, offset: int = 0) -> list[Follow]:
        """Get publishers subscribers"""
        where = "publisher = %(publisher)s"
        params: dict[str, str | int] = {"publisher": publisher}
        if limit is not None:
            where += " LIMIT %(limit)s"
            params["limit"] = limit
        if offset:
            where += " OFFSET %(offset)s"
            params["offset"] = offset
        query = f"SELECT subscriber, publisher, disabled, created, updated FROM {cls.TABLENAME} WHERE {where}"
        return [web.storage(row) for row in await fetch_all(query, params)]

    @classmethod
    def get_followers_sync(cls, publisher: str, limit: int | None = None, offset: int = 0) -> list[Follow]:
        return async_bridge.run(cls.get_followers(publisher, limit, offset))

    @classmethod
    async def get_following(cls, subscriber: str, limit: int | None = None, offset: int = 0, exclude_disabled: bool = False) -> list[Follow]:
        """Get subscriber's subscriptions"""
        where = "subscriber = %(subscriber)s"
        params: dict[str, str | int | bool] = {"subscriber": subscriber}
        if exclude_disabled:
            where += " AND disabled = false"
        if limit is not None:
            where += " LIMIT %(limit)s"
            params["limit"] = limit
        if offset:
            where += " OFFSET %(offset)s"
            params["offset"] = offset
        query = f"SELECT subscriber, publisher, disabled, created, updated FROM {cls.TABLENAME} WHERE {where}"
        return await fetch_all(query, params)

    @classmethod
    def get_following_sync(cls, subscriber: str, limit: int | None = None, offset: int = 0, exclude_disabled: bool = False) -> list[Follow]:
        return async_bridge.run(cls.get_following(subscriber, limit, offset, exclude_disabled))

    @classmethod
    async def toggle_privacy(cls, publisher: str, private: bool = True) -> None:
        await execute(
            f"UPDATE {cls.TABLENAME} SET disabled = %(disabled)s WHERE publisher = %(publisher)s",
            {"disabled": private, "publisher": publisher},
        )

    @classmethod
    def toggle_privacy_sync(cls, publisher: str, private: bool = True) -> None:
        async_bridge.run(cls.toggle_privacy(publisher, private))

    @classmethod
    async def get_feed(cls, subscriber: str, limit: int = 25, offset: int = 0) -> list[dict]:
        # Get subscriber's subscriptions
        subscriptions = await cls.get_following(subscriber, exclude_disabled=True)

        # Extract usernames from subscriptions
        usernames = [sub["publisher"] for sub in subscriptions]

        if not usernames:
            return []

        # Formulate the SQL query to get latest 25 entries for subscribed users
        query = "SELECT * FROM bookshelves_books WHERE username = ANY(%(usernames)s) ORDER BY created DESC LIMIT %(limit)s OFFSET %(offset)s"
        # Fetch the recent books for subscribed users
        recent_books = [web.storage(row) for row in await fetch_all(query, {"usernames": usernames, "limit": limit, "offset": offset})]

        # Add keys
        for i, rb in enumerate(recent_books):
            rb["key"] = f"/works/OL{rb['work_id']}W"

        from openlibrary.core.bookshelves import Bookshelves

        await Bookshelves.add_solr_works_async(recent_books)

        return recent_books

    @classmethod
    def get_feed_sync(cls, subscriber: str, limit: int = 25, offset: int = 0) -> list[dict]:
        return async_bridge.run(cls.get_feed(subscriber, limit, offset))

    @classmethod
    async def count_following(cls, subscriber: str) -> int:
        query = f"SELECT count(*) as count FROM {cls.TABLENAME} WHERE subscriber = %(subscriber)s"
        row = await fetch_one(query, {"subscriber": subscriber})
        assert row is not None
        return row["count"]

    @classmethod
    def count_following_sync(cls, subscriber: str) -> int:
        return async_bridge.run(cls.count_following(subscriber))

    @classmethod
    async def count_followers(cls, publisher: str) -> int:
        query = f"SELECT count(*) as count FROM {cls.TABLENAME} WHERE publisher = %(publisher)s"
        row = await fetch_one(query, {"publisher": publisher})
        assert row is not None
        return row["count"]

    @classmethod
    def count_followers_sync(cls, publisher: str) -> int:
        return async_bridge.run(cls.count_followers(publisher))

    @classmethod
    async def summary(cls) -> dict:
        row = await fetch_one(
            f"SELECT "
            f" count(DISTINCT subscriber) AS total,"
            f" count(DISTINCT subscriber) FILTER (WHERE created >= %(month_ago)s) AS month,"
            f" count(DISTINCT subscriber) FILTER (WHERE created >= %(week_ago)s) AS week"
            f" FROM {cls.TABLENAME}",
            {"month_ago": DATE_ONE_MONTH_AGO, "week_ago": DATE_ONE_WEEK_AGO},
        )
        assert row is not None
        return {
            "total_following_count": {
                "total": row["total"],
                "month": row["month"],
                "week": row["week"],
            }
        }

    @classmethod
    def summary_sync(cls) -> dict:
        return async_bridge.run(cls.summary())

    @classmethod
    async def is_following(cls, username: str) -> bool:
        query = f"SELECT EXISTS(SELECT 1 FROM {cls.TABLENAME} WHERE subscriber = %(subscriber)s)"
        row = await fetch_one(query, {"subscriber": username})
        assert row is not None
        return row["exists"]

    @classmethod
    def is_following_sync(cls, username: str) -> bool:
        return async_bridge.run(cls.is_following(username))
