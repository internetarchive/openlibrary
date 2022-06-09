import logging
from datetime import date
from typing import Literal, Optional, cast
from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

from . import db

logger = logging.getLogger(__name__)


class Bookshelves(db.CommonExtras):

    TABLENAME = "bookshelves_books"
    PRIMARY_KEY = ["username", "work_id", "bookshelf_id"]
    PRESET_BOOKSHELVES = {'Want to Read': 1, 'Currently Reading': 2, 'Already Read': 3}
    ALLOW_DELETE_ON_CONFLICT = True

    PRESET_BOOKSHELVES_JSON = {
        'want_to_read': 1,
        'currently_reading': 2,
        'already_read': 3,
    }

    @classmethod
    def summary(cls):
        return {
            'total_books_logged': {
                'total': Bookshelves.total_books_logged(),
                'month': Bookshelves.total_books_logged(since=DATE_ONE_MONTH_AGO),
                'week': Bookshelves.total_books_logged(since=DATE_ONE_WEEK_AGO),
            },
            'total_users_logged': {
                'total': Bookshelves.total_unique_users(),
                'month': Bookshelves.total_unique_users(since=DATE_ONE_MONTH_AGO),
                'week': Bookshelves.total_unique_users(since=DATE_ONE_WEEK_AGO),
            },
        }

    @classmethod
    def total_books_logged(cls, shelf_ids: list[str] = None, since: date = None) -> int:
        """Returns (int) number of books logged across all Reading Log shelves (e.g. those
        specified in PRESET_BOOKSHELVES). One may alternatively specify a
        `list` of `shelf_ids` to isolate or span multiple
        shelves. `since` may be used to limit the result to those
        books logged since a specific date. Any python datetime.date
        type should work.

        :param shelf_ids: one or more bookshelf_id values, see also the default values
            specified in PRESET_BOOKSHELVES
        :param since: returns all logged books after date
        """

        oldb = db.get_db()
        query = "SELECT count(*) from bookshelves_books"
        if shelf_ids:
            query += " WHERE bookshelf_id IN ($shelf_ids)"
            if since:
                query += " AND created >= $since"
        elif since:
            query += " WHERE created >= $since"
        results = cast(
            tuple[int],
            oldb.query(query, vars={'since': since, 'shelf_ids': shelf_ids}),
        )
        return results[0]

    @classmethod
    def total_unique_users(cls, since: date = None) -> int:
        """Returns the total number of unique users who have logged a
        book. `since` may be provided to only return the number of users after
        a certain datetime.date.
        """
        oldb = db.get_db()
        query = "select count(DISTINCT username) from bookshelves_books"
        if since:
            query += " WHERE created >= $since"
        results = cast(tuple[int], oldb.query(query, vars={'since': since}))
        return results[0]

    @classmethod
    def most_logged_books(
        cls, shelf_id='', limit=10, since: date = None, page=1, fetch=False
    ) -> list:
        """Returns a ranked list of work OLIDs (in the form of an integer --
        i.e. OL123W would be 123) which have been most logged by
        users. This query is limited to a specific shelf_id (e.g. 1
        for "Want to Read").
        """
        offset = (page - 1) * limit
        oldb = db.get_db()
        where = 'WHERE bookshelf_id' + ('=$shelf_id' if shelf_id else ' IS NOT NULL ')
        if since:
            where += ' AND created >= $since'
        query = f'select work_id, count(*) as cnt from bookshelves_books {where}'
        query += ' group by work_id order by cnt desc limit $limit offset $offset'
        logger.info("Query: %s", query)
        logged_books = list(
            oldb.query(
                query, vars={'shelf_id': shelf_id, 'limit': limit, 'offset': offset, 'since': since}
            )
        )
        return cls.fetch(logged_books) if fetch else logged_books

    @classmethod
    def fetch(cls, readinglog_items):
        """Given a list of readinglog_items, such as those returned by
        Bookshelves.most_logged_books, fetch the corresponding Open Library
        book records from solr with availability
        """
        from openlibrary.plugins.worksearch.code import get_solr_works
        from openlibrary.core.lending import get_availabilities

        # This gives us a dict of all the works representing
        # the logged_books, keyed by work_id
        work_index = get_solr_works(
            f"/works/OL{i['work_id']}W"
            for i in readinglog_items
        )

        # Loop over each work in the index and inject its availability
        availability_index = get_availabilities(work_index.values())
        for work_key in availability_index:
            work_index[work_key]['availability'] = availability_index[work_key]

        # Return items from the work_index in the order
        # they are represented by the trending logged books
        for i, item in enumerate(readinglog_items):
            key = f"/works/OL{item['work_id']}W"
            if key in work_index:
                readinglog_items[i]['work'] = work_index[key]
        return readinglog_items

    @classmethod
    def count_total_books_logged_by_user(
        cls, username: str, bookshelf_ids: list[str] = None
    ) -> int:
        """Counts the (int) total number of books logged by this `username`,
        with the option of limiting the count to specific bookshelves
        by `bookshelf_id`
        """
        return sum(
            cls.count_total_books_logged_by_user_per_shelf(
                username, bookshelf_ids=bookshelf_ids
            ).values()
        )

    @classmethod
    def count_total_books_logged_by_user_per_shelf(
        cls, username: str, bookshelf_ids: list[str] = None
    ) -> dict[str, int]:
        """Returns a dict mapping the specified user's bookshelves_ids to the
        number of number of books logged per each shelf, i.e. {bookshelf_id:
        count}. By default, we limit bookshelf_ids to those in PRESET_BOOKSHELVES

        TODO: add `since` to fetch books logged after a certain
        date. Useful for following/subscribing-to users and being
        notified of books they log. Also add to
        count_total_books_logged_by_user
        """
        oldb = db.get_db()
        data = {'username': username}
        _bookshelf_ids = ','.join(
            [str(x) for x in bookshelf_ids or cls.PRESET_BOOKSHELVES.values()]
        )
        query = (
            "SELECT bookshelf_id, count(*) from bookshelves_books WHERE "
            "bookshelf_id=ANY('{" + _bookshelf_ids + "}'::int[]) "
            "AND username=$username GROUP BY bookshelf_id"
        )
        result = oldb.query(query, vars=data)
        return {i['bookshelf_id']: i['count'] for i in result} if result else {}

    @classmethod
    def get_users_logged_books(
        cls,
        username: str,
        bookshelf_id: str = None,
        limit=100,
        page=1,
        sort: Literal['created asc', 'created desc'] = 'created desc',
    ) -> list:
        """Returns a list of Reading Log database records for books which
        the user has logged. Records are described in core/schema.py
        and include:

        :param username: who logged this book
        :param work_id: the Open Library work ID as an int (e.g. OL123W becomes 123)
        :param bookshelf_id: the ID of the bookshelf, see: PRESET_BOOKSHELVES.
            If bookshelf_id is None, return books from all bookshelves.
        :param edition_id: the specific edition logged, if applicable
        :param created: date the book was logged

        """
        oldb = db.get_db()
        page = int(page or 1)
        data = {
            'username': username,
            'limit': limit,
            'offset': limit * (page - 1),
            'bookshelf_id': bookshelf_id,
        }
        if sort == 'created desc':
            query = (
                "SELECT * from bookshelves_books WHERE "
                "bookshelf_id=$bookshelf_id AND username=$username "
                "ORDER BY created DESC "
                "LIMIT $limit OFFSET $offset"
            )
        else:
            query = (
                "SELECT * from bookshelves_books WHERE "
                "bookshelf_id=$bookshelf_id AND username=$username "
                "ORDER BY created ASC "
                "LIMIT $limit OFFSET $offset"
            )
        if not bookshelf_id:
            query = "SELECT * from bookshelves_books WHERE username=$username"
            # XXX Removing limit, offset, etc from data looks like a bug
            # unrelated / not fixing in this PR.
            data = {'username': username}
        return list(oldb.query(query, vars=data))

    @classmethod
    def get_recently_logged_books(cls, bookshelf_id=None, limit=50, page=1, fetch=False) -> list:
        oldb = db.get_db()
        page = int(page or 1)
        data = {
            'bookshelf_id': bookshelf_id,
            'limit': limit,
            'offset': limit * (page - 1),
        }
        where = "WHERE bookshelf_id=$bookshelf_id " if bookshelf_id else ""
        query = (
            f"SELECT * from bookshelves_books {where} "
            "ORDER BY created DESC LIMIT $limit OFFSET $offset"
        )
        logged_books = list(oldb.query(query, vars=data))
        return cls.fetch(logged_books) if fetch else logged_books

    @classmethod
    def get_users_read_status_of_work(
        cls, username: str, work_id: str
    ) -> Optional[str]:
        """A user can mark a book as (1) want to read, (2) currently reading,
        or (3) already read. Each of these states is mutually
        exclusive. Returns the user's read state of this work, if one
        exists.
        """
        oldb = db.get_db()
        data = {'username': username, 'work_id': int(work_id)}
        bookshelf_ids = ','.join([str(x) for x in cls.PRESET_BOOKSHELVES.values()])
        query = (
            "SELECT bookshelf_id from bookshelves_books WHERE "
            "bookshelf_id=ANY('{" + bookshelf_ids + "}'::int[]) "
            "AND username=$username AND work_id=$work_id"
        )
        result = list(oldb.query(query, vars=data))
        return result[0].bookshelf_id if result else None

    @classmethod
    def get_users_read_status_of_works(cls, username: str, work_ids: list[str]) -> list:
        oldb = db.get_db()
        data = {
            'username': username,
            'work_ids': work_ids,
        }
        query = (
            "SELECT work_id, bookshelf_id from bookshelves_books WHERE "
            "username=$username AND "
            "work_id IN $work_ids"
        )
        return list(oldb.query(query, vars=data))

    @classmethod
    def add(
        cls, username: str, bookshelf_id: str, work_id: str, edition_id=None
    ) -> None:
        """Adds a book with `work_id` to user's bookshelf designated by
        `bookshelf_id`"""
        oldb = db.get_db()
        work_id = int(work_id)  # type: ignore
        bookshelf_id = int(bookshelf_id)  # type: ignore
        data = {
            'work_id': work_id,
            'username': username,
        }

        users_status = cls.get_users_read_status_of_work(username, work_id)
        if not users_status:
            return oldb.insert(
                cls.TABLENAME,
                username=username,
                bookshelf_id=bookshelf_id,
                work_id=work_id,
                edition_id=edition_id,
            )
        else:
            where = "work_id=$work_id AND username=$username"
            return oldb.update(
                cls.TABLENAME,
                where=where,
                bookshelf_id=bookshelf_id,
                edition_id=edition_id,
                vars=data,
            )

    @classmethod
    def remove(cls, username: str, work_id: str, bookshelf_id: str = None):
        oldb = db.get_db()
        where = {'username': username, 'work_id': int(work_id)}
        if bookshelf_id:
            where['bookshelf_id'] = int(bookshelf_id)

        try:
            return oldb.delete(
                cls.TABLENAME,
                where=('work_id=$work_id AND username=$username'),
                vars=where,
            )
        except:  # we want to catch no entry exists
            return None

    @classmethod
    def get_works_shelves(cls, work_id: str, lazy: bool = False):
        """Bookshelves this work is on"""
        oldb = db.get_db()
        query = f"SELECT * from {cls.TABLENAME} where work_id=$work_id"
        try:
            result = oldb.query(query, vars={'work_id': work_id})
            return result if lazy else list(result)
        except:
            return None

    @classmethod
    def get_num_users_by_bookshelf_by_work_id(cls, work_id: str) -> dict[str, int]:
        """Returns a dict mapping a work_id to the
        number of number of users who have placed that work_id in each shelf,
        i.e. {bookshelf_id: count}.
        """
        oldb = db.get_db()
        query = (
            "SELECT bookshelf_id, count(DISTINCT username) as user_count "
            "from bookshelves_books where"
            " work_id=$work_id"
            " GROUP BY bookshelf_id"
        )
        result = oldb.query(query, vars={'work_id': int(work_id)})
        return {i['bookshelf_id']: i['user_count'] for i in result} if result else {}

    @classmethod
    def user_with_most_books(cls) -> list:
        """
        Which super patrons have the most books logged?

        SELECT username, count(*) AS counted from bookshelves_books
          WHERE bookshelf_id=ANY('{1,3,2}'::int[]) GROUP BY username
            ORDER BY counted DESC, username LIMIT 10
        """
        oldb = db.get_db()
        _bookshelf_ids = ','.join([str(x) for x in cls.PRESET_BOOKSHELVES.values()])
        query = (
            "SELECT username, count(*) AS counted "
            "FROM bookshelves_books WHERE "
            "bookshelf_id=ANY('{" + _bookshelf_ids + "}'::int[]) "
            "GROUP BY username "
            "ORDER BY counted DESC, username LIMIT 100"
        )
        result = oldb.query(query)
        return list(result)
