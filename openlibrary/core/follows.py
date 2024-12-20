import logging
from typing import cast

from openlibrary.core.bookshelves import Bookshelves
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

from . import db

logger = logging.getLogger(__name__)


class PubSub:
    TABLENAME = "follows"
    PRIMARY_KEY = ["subscriber", "publisher"]

    @classmethod
    def subscribe(cls, subscriber, publisher):
        oldb = db.get_db()
        return oldb.insert(cls.TABLENAME, subscriber=subscriber, publisher=publisher)

    @classmethod
    def unsubscribe(cls, subscriber, publisher):
        oldb = db.get_db()
        return oldb.delete(
            cls.TABLENAME,
            where='subscriber=$subscriber AND publisher=$publisher',
            vars={'subscriber': subscriber, 'publisher': publisher},
        )

    @classmethod
    def is_subscribed(cls, subscriber, publisher):
        oldb = db.get_db()
        subscription = oldb.select(
            cls.TABLENAME,
            where='subscriber=$subscriber AND publisher=$publisher',
            vars={'subscriber': subscriber, 'publisher': publisher},
            limit=1,  # Limiting to 1 result to check if the subscription exists
        )
        return len(subscription)

    @classmethod
    def get_followers(cls, publisher, limit=None, offset=0):
        """Get publishers subscribers"""
        oldb = db.get_db()
        where = 'publisher=$publisher'
        subscribers = oldb.select(
            cls.TABLENAME,
            where=where,
            vars={'publisher': publisher},
            limit=limit,
            offset=offset,
        )
        return subscribers

    @classmethod
    def get_following(cls, subscriber, limit=None, offset=0, exclude_disabled=False):
        """Get subscriber's subscriptions"""
        oldb = db.get_db()
        where = 'subscriber=$subscriber'
        if exclude_disabled:
            where += " AND disabled=false"
        subscriptions = oldb.select(
            cls.TABLENAME,
            where=where,
            vars={'subscriber': subscriber},
            limit=limit,
            offset=offset,
        )
        return [dict(s) for s in subscriptions]

    @classmethod
    def toggle_privacy(cls, publisher, private=True):
        oldb = db.get_db()
        return oldb.update(
            cls.TABLENAME,
            disabled=private,
            where="publisher=$publisher",
            vars={"publisher": publisher},
        )

    @classmethod
    def get_feed(cls, subscriber, limit=25, offset=0):
        oldb = db.get_db()

        # Get subscriber's subscriptions
        subscriptions = cls.get_following(subscriber, exclude_disabled=True)

        # Extract usernames from subscriptions
        usernames = [sub['publisher'] for sub in subscriptions]

        if not usernames:
            return []

        # Formulate the SQL query to get latest 25 entries for subscribed users
        query = (
            "SELECT * FROM bookshelves_books WHERE username IN $usernames"
            " ORDER BY created DESC LIMIT $limit OFFSET $offset"
        )
        # Fetch the recent books for subscribed users
        recent_books = list(
            oldb.query(
                query,
                vars={'usernames': usernames, 'limit': limit, 'offset': offset},
            )
        )

        # Add keys
        for i, rb in enumerate(recent_books):
            recent_books[i].key = f'/works/OL{rb.work_id}W'

        return Bookshelves.fetch(recent_books)

    @classmethod
    def count_following(cls, subscriber):
        oldb = db.get_db()
        count = oldb.select(
            cls.TABLENAME,
            what='count(*) as count',
            where='subscriber=$subscriber',
            vars={'subscriber': subscriber},
        )
        return cast(tuple[int], count)[0].get('count', 0)

    @classmethod
    def count_followers(cls, publisher):
        oldb = db.get_db()
        count = oldb.select(
            cls.TABLENAME,
            what='count(*) as count',
            where='publisher=$publisher',
            vars={'publisher': publisher},
        )
        return cast(tuple[int], count)[0].get('count', 0)

    @classmethod
    def total_followers(cls, since=None) -> int:
        oldb = db.get_db()
        query = f"SELECT count(DISTINCT subscriber) from {cls.TABLENAME}"
        if since:
            query += " WHERE created >= $since"
        results = oldb.query(query, vars={'since': since})
        return results[0]['count'] if results else 0

    @classmethod
    def summary(cls):
        return {
            "total_following_count": {
                "total": cls.total_followers(),
                "month": cls.total_followers(since=DATE_ONE_MONTH_AGO),
                "week": cls.total_followers(since=DATE_ONE_WEEK_AGO),
            }
        }

    @classmethod
    def count_total_subscribers(cls):
        oldb = db.get_db()
        count = oldb.query("SELECT COUNT(DISTINCT subscriber) AS count FROM follows")
        return cast(tuple[int], count)[0].get('count', 0)

    @classmethod
    def count_total_publishers(cls):
        oldb = db.get_db()
        count = oldb.query("SELECT COUNT(DISTINCT publisher) AS count FROM follows")
        return cast(tuple[int], count)[0].get('count', 0)

    @classmethod
    def most_followed(cls, limit=100):
        oldb = db.get_db()
        top_publishers = oldb.query(
            "SELECT publisher, COUNT(*) AS count FROM follows WHERE disabled=false GROUP BY publisher ORDER BY count DESC LIMIT $limit",
            vars={'limit': limit},
        )
        return top_publishers
