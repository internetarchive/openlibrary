"""Shared base class for Bookshelves, Booknotes, Ratings, and Observations.

Extracts duplicated query methods (total_unique_users, total_count, most_popular)
that were previously copy-pasted across each subclass with only the table name differing.

See the XXX comment in booknotes.py:42 which originally identified this duplication.
"""

from __future__ import annotations

from . import db


class BookDBModel(db.CommonExtras):
    """Base class for book-related database models.

    Subclasses must set TABLENAME and PRIMARY_KEY (inherited from CommonExtras).
    """

    TABLENAME: str
    PRIMARY_KEY: tuple[str, ...]

    @classmethod
    def total_unique_users(cls, since=None) -> int:
        """Returns the total number of unique users who have records in this table.

        Identical across Booknotes, Bookshelves, and Ratings — only the table name differs.
        """
        oldb = db.get_db()
        query = f"select count(DISTINCT username) from {cls.TABLENAME}"
        if since:
            query += " WHERE created >= $since"
        results = oldb.query(query, vars={"since": since})
        return results[0]["count"] if results else 0

    @classmethod
    def total_count(cls, since=None) -> int:
        """Returns the total number of records in this table.

        Shared by Booknotes.total_booknotes() and Ratings.total_num_books_rated().
        """
        oldb = db.get_db()
        query = f"SELECT count(*) from {cls.TABLENAME}"
        if since:
            query += " WHERE created >= $since"
        results = oldb.query(query, vars={"since": since})
        return results[0]["count"] if results else 0

    @classmethod
    def most_popular(cls, limit=10, since=False):
        """Returns work_ids ranked by count, descending.

        Shared by Booknotes.most_notable_books(), Bookshelves.most_logged_books(),
        and Ratings.most_rated_books().
        """
        oldb = db.get_db()
        query = f"select work_id, count(*) as cnt from {cls.TABLENAME}"
        if since:
            query += " WHERE created >= $since"
        query += " group by work_id order by cnt desc limit $limit"
        return list(oldb.query(query, vars={"limit": limit, "since": since}))
