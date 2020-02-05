from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

from . import db


class Bookshelves(object):

    PRESET_BOOKSHELVES = {
        'Want to Read': 1,
        'Currently Reading': 2,
        'Already Read': 3
    }

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
                'week': Bookshelves.total_books_logged(since=DATE_ONE_WEEK_AGO)
            },
            'total_users_logged': {
                'total': Bookshelves.total_unique_users(),
                'month': Bookshelves.total_unique_users(since=DATE_ONE_MONTH_AGO),
                'week': Bookshelves.total_unique_users(since=DATE_ONE_WEEK_AGO)
            }
        }

    @classmethod
    def total_books_logged(cls, shelf_ids=None, since=None):
        """Returns (int) number of books logged across all Reading Log shelves (e.g. those
        specified in PRESET_BOOKSHELVES). One may alternatively specify a
        `list` of `shelf_ids` to isolate or span multiple
        shelves. `since` may be used to limit the result to those
        books logged since a specific date. Any python datetime.date
        type should work.

        Args:
            shelf_ids (list) - one or more bookshelf_id values, see
                also the default values specified in PRESET_BOOKSHELVES
            since (datetime.date) - returns all logged books after date

        """

        oldb = db.get_db()
        query = "SELECT count(*) from bookshelves_books"
        if shelf_ids:
            query += " WHERE bookshelf_id IN ($shelf_ids)"
            if since:
                query += " AND created >= $since"
        elif since:
            query += " WHERE created >= $since"
        results = oldb.query(query, vars={'since': since, 'shelf_ids': shelf_ids})
        return results[0] if results else None

    @classmethod
    def total_unique_users(cls, since=None):
        """Returns the total number of unique users who have logged a
        book. `since` may be provided to only return the number of users after
        a certain datetime.date.
        """
        oldb = db.get_db()
        query = "select count(DISTINCT username) from bookshelves_books"
        if since:
            query += " WHERE created >= $since"
        results = oldb.query(query, vars={'since': since})
        return results[0] if results else None

    @classmethod
    def most_logged_books(cls, shelf_id, limit=10, since=False):
        """Returns a ranked list of work OLIDs (in the form of an integer --
        i.e. OL123W would be 123) which have been most logged by
        users. This query is limited to a specific shelf_id (e.g. 1
        for "Want to Read").
        """
        oldb = db.get_db()
        query = 'select work_id, count(*) as cnt from bookshelves_books WHERE bookshelf_id=$shelf_id '
        if since:
            query += " AND created >= $since"
        query += ' group by work_id order by cnt desc limit $limit'
        return list(oldb.query(query, vars={'shelf_id': shelf_id, 'limit': limit, 'since': since}))

    @classmethod
    def count_total_books_logged_by_user(cls, username, bookshelf_ids=None):
        """Counts the (int) total number of books logged by this `username`,
        with the option of limiting the count to specific bookshelves
        by `bookshelf_id`
        """
        return sum(cls.count_total_books_logged_by_user_per_shelf(
            username, bookshelf_ids=bookshelf_ids).values())

    @classmethod
    def count_total_books_logged_by_user_per_shelf(cls, username, bookshelf_ids=None):
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
        _bookshelf_ids = ','.join([str(x) for x in bookshelf_ids or cls.PRESET_BOOKSHELVES.values()])
        query = ("SELECT bookshelf_id, count(*) from bookshelves_books WHERE "
                 "bookshelf_id=ANY('{" + _bookshelf_ids + "}'::int[]) "
                 "AND username=$username GROUP BY bookshelf_id")
        result = oldb.query(query, vars=data)
        return dict([(i['bookshelf_id'], i['count']) for i in result]) if result else {}

    @classmethod
    def get_users_logged_books(cls, username, bookshelf_id, limit=100, page=1):
        """Returns a list of Reading Log database records for books which the user has logged. Records are described in core/schema.py and include:

        username (str) - who logged this book
        work_id (int) - the Open Library work ID as an int (e.g. OL123W becomes 123)
        bookshelf_id (int) - the ID of the bookshelf, see: PRESET_BOOKSHELVES
        edition_id (int) [optional] - the specific edition logged, if applicable
        created (datetime) - date the book was logged
        """
        oldb = db.get_db()
        page = int(page) if page else 1
        data = {
            'username': username,
            'limit': limit,
            'offset': limit * (page - 1),
            'bookshelf_id': bookshelf_id
        }
        query = ("SELECT * from bookshelves_books WHERE "
                 "bookshelf_id=$bookshelf_id AND username=$username "
                 "LIMIT $limit OFFSET $offset")
        return list(oldb.query(query, vars=data))

    @classmethod
    def get_users_read_status_of_work(cls, username, work_id):
        """A user can mark a book as (1) want to read, (2) currently reading,
        or (3) already read. Each of these states is mutually
        exclusive. Returns the user's read state of this work, if one
        exists.
        """
        oldb = db.get_db()
        data = {
            'username': username,
            'work_id': int(work_id)
        }
        bookshelf_ids = ','.join([str(x) for x in cls.PRESET_BOOKSHELVES.values()])
        query = ("SELECT bookshelf_id from bookshelves_books WHERE "
                 "bookshelf_id=ANY('{" + bookshelf_ids + "}'::int[]) "
                 "AND username=$username AND work_id=$work_id")
        result = list(oldb.query(query, vars=data))
        return result[0].bookshelf_id if result else None

    @classmethod
    def add(cls, username, bookshelf_id, work_id, edition_id=None):
        """Adds a book with `work_id` to user's bookshelf designated by
        `bookshelf_id`"""
        oldb = db.get_db()
        work_id = int(work_id)
        bookself_id = int(bookshelf_id)
        data = {'work_id': work_id, 'username': username}

        users_status = cls.get_users_read_status_of_work(username, work_id)
        if not users_status:
            return oldb.insert('bookshelves_books', username=username,
                               bookshelf_id=bookshelf_id,
                               work_id=work_id, edition_id=edition_id)
        else:
            where = "work_id=$work_id AND username=$username"
            return oldb.update('bookshelves_books', where=where,
                               bookshelf_id=bookshelf_id, vars=data)

    @classmethod
    def remove(cls, username, work_id, bookshelf_id=None):
        oldb = db.get_db()
        where = {
            'username': username,
            'work_id': int(work_id)
        }
        if bookshelf_id:
            where['bookshelf_id'] = int(bookshelf_id)

        try:
            return oldb.delete('bookshelves_books',
                               where=('work_id=$work_id AND username=$username'), vars=where)
        except:  # we want to catch no entry exists
            return None

    @classmethod
    def get_works_shelves(cls, work_id, lazy=False):
        """Bookshelves this work is on"""
        oldb = db.get_db()
        query = "SELECT * from bookshelves_books where work_id=$work_id"
        try:
            result = oldb.query(query, vars={'work_id': int(work_id)})
            return result if lazy else list(result)
        except:
            return None

    @classmethod
    def get_num_users_by_bookshelf_by_work_id(cls, work_id):
        """Returns a dict mapping a work_id to the
        number of number of users who have placed that work_id in each shelf, i.e. {bookshelf_id:
        count}.
        """
        oldb = db.get_db()
        query = ("SELECT bookshelf_id, count(DISTINCT username) as user_count from bookshelves_books where"
                 " work_id=$work_id"
                 " GROUP BY bookshelf_id")
        result = oldb.query(query, vars={'work_id': int(work_id)})
        return dict([(i['bookshelf_id'], i['user_count']) for i in result]) if result else {}

    @classmethod
    def user_with_most_books(cls):
        """
        Which super patrons have the most books logged?

        SELECT username, count(*) AS counted from bookshelves_books WHERE bookshelf_id=ANY('{1,3,2}'::int[]) GROUP BY username ORDER BY counted DESC, username LIMIT 10
        """
        oldb = db.get_db()
        _bookshelf_ids = ','.join([str(x) for x in cls.PRESET_BOOKSHELVES.values()])
        query = ("SELECT username, count(*) AS counted "
                 "FROM bookshelves_books WHERE "
                 "bookshelf_id=ANY('{" + _bookshelf_ids + "}'::int[]) "
                 "GROUP BY username "
                 "ORDER BY counted DESC, username LIMIT 100")
        result = oldb.query(query)
        return list(result)

    @classmethod
    def search_my_readinglog(cls, q, bookshelf_id):
        oldb = db.get_db()
        pass
