import logging
import web
from typing import cast, Any
from openlibrary.core.bookshelves import Bookshelves
    
from . import db

logger = logging.getLogger(__name__)


class PubSub(db.CommonExtras):
    TABLENAME = "follows"
    PRIMARY_KEY = ["subscriber", "publisher"]

    @classmethod
    def subscribe(cls, subscriber, publisher):
        oldb = db.get_db()
        return oldb.insert(
            cls.TABLENAME,
            subscriber=subscriber,
            publisher=publisher
        )
    
    @classmethod
    def unsubscribe(cls, subscriber, publisher):
        oldb = db.get_db()
        try:
            return oldb.delete(
                cls.TABLENAME,
                where='subscriber=$subscriber AND publisher=$publisher',
                vars={'subscriber': subscriber, 'publisher': publisher}
            )
        except Exception:
            return None

    @classmethod
    def is_subscribed(cls, subscriber, publisher):
        oldb = db.get_db()
        subscription = oldb.select(
            cls.TABLENAME,
            where='subscriber=$subscriber AND publisher=$publisher',
            vars={'subscriber': subscriber, 'publisher': publisher},
            limit=1  # Limiting to 1 result to check if the subscription exists
        )
        return len(subscription)

    @classmethod
    def get_subscribers(cls, publisher):
        """Get publishers subscribers"""
        oldb = db.get_db()
        subscribers = oldb.select(
            cls.TABLENAME,
            where='publisher=$publisher',
            vars={'publisher': publisher}
        )
        return subscribers

    @classmethod
    def get_subscriptions(cls, subscriber):
        """Get subscriber's subscriptions"""
        oldb = db.get_db()
        subscriptions = oldb.select(
            cls.TABLENAME,
            where='subscriber=$subscriber',
            vars={'subscriber': subscriber}
        )
        return [dict(s) for s in subscriptions]

    @classmethod
    def get_feed(cls, subscriber, limit=25, offset=0):
        oldb = db.get_db()

        # Get subscriber's subscriptions
        subscriptions = cls.get_subscriptions(subscriber)

        # Extract usernames from subscriptions
        usernames = [sub['publisher'] for sub in subscriptions]

        # Remove any user that are private...
        public_usernames = [
            p.key.split('/')[2] for p in web.ctx.site.get_many([
                f'/people/{u}/preferences' for u in usernames
            ])
            if p.dict().get('notifications', {}).get('public_readlog') == 'yes'
        ]

        # Formulate the SQL query to get latest 25 entries for subscribed users
        query = (
            "SELECT * FROM bookshelves_books WHERE username IN $usernames"
            " ORDER BY created DESC LIMIT $limit OFFSET $offset"
        )
        # Fetch the recent books for subscribed users
        recent_books = list(oldb.query(query, vars={
            'usernames': public_usernames, 'limit': limit, 'offset': offset
        }))

        # Add keys
        for i, rb in enumerate(recent_books):
            recent_books[i].key = f'/works/OL{recent_books[i].work_id}W'

        return Bookshelves.fetch(recent_books)

    @classmethod
    def count_subscriptions(cls, subscriber):
        oldb = db.get_db()
        count = oldb.select(
            cls.TABLENAME,
            what='count(*) as count',
            where='subscriber=$subscriber',
            vars={'subscriber': subscriber}
        )
        return cast(tuple[int], count)[0]

    @classmethod
    def count_subscribers(cls, publisher):
        oldb = db.get_db()
        count = oldb.select(
            cls.TABLENAME,
            what='count(*) as count',
            where='publisher = $publisher',
            vars={'publisher': publisher}
        )
        return cast(tuple[int], count)[0]

    @classmethod
    def count_total_subscribers(cls):
        oldb = db.get_db()
        count = oldb.query("SELECT COUNT(DISTINCT subscriber) AS count FROM follows")
        return cast(tuple[int], count)[0]

    @classmethod
    def count_total_publishers(cls):
        oldb = db.get_db()
        count = oldb.query("SELECT COUNT(DISTINCT publisher) AS count FROM follows")
        return cast(tuple[int], count)[0]
    
    @classmethod
    def top_publishers(cls, limit=100):
        oldb = db.get_db()
        top_publishers = oldb.query(
            "SELECT publisher, COUNT(*) AS count FROM follows GROUP BY publisher ORDER BY count DESC LIMIT $limit",
            vars={'limit': limit}
        )
        #return [(publisher.publisher, publisher.count) for publisher in publishers]
        return top_publishers  
