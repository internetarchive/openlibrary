from . import db

class Bookshelves(object):

    PRESET_BOOKSHELVES = {
        'Want to Read': 1,
        'Currently Reading': 2,
        'Already Read': 3
    }

    @classmethod
    def total_books_logged(cls, shelf_ids=None, since=None):
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
        oldb = db.get_db()
        query = "select count(DISTINCT username) from bookshelves_books"
        if since:
            query += " WHERE created >= $since"
        results = oldb.query(query, vars={'since': since})
        return results[0] if results else None

    @classmethod
    def most_logged_books(cls, shelf_id, limit=10, since=False):
        oldb = db.get_db()
        query = 'select work_id, count(*) as cnt from bookshelves_books where bookshelf_id=$shelf_id group by work_id order by cnt desc limit $limit'
        if since:
            query += " WHERE created >= $since"
        return list(oldb.query(query, vars={'shelf_id': shelf_id, 'limit': limit, 'since': since}))

    @classmethod
    def count_users_readlogs(cls, username, bookshelf_id=None, count_per_shelf=False):
        oldb = db.get_db()
        data = {'username': username}
        bookshelf_ids = ','.join([str(x) for x in cls.PRESET_BOOKSHELVES.values()])
        query = ("SELECT bookshelf_id, count(*) from bookshelves_books WHERE "
                 "bookshelf_id=ANY('{" + bookshelf_ids + "}'::int[]) "
                 "AND username=$username")
        if bookshelf_id:
            data['bookshelf_id'] = bookshelf_id
            query += ' AND bookshelf_id=$bookshelf_id'
        elif count_per_shelf:
            query += ' GROUP BY bookshelf_id'

        result = oldb.query(query, vars=data)
        if result:
            if count_per_shelf:
                return dict([(i['bookshelf_id'], i['count']) for i in result])
            return result[0]['count']
        return None

    @classmethod
    def get_users_reads(cls, username, bookshelf_id=None, limit=100, page=1):
        """Returns a list of books the user has, is, or wants to read
        """
        oldb = db.get_db()
        page = int(page) if page else 1
        offset = limit * (page - 1)
        data = {
            'username': username,
            'limit': limit,
            'offset': offset
        }
        bookshelf_ids = ','.join([str(x) for x in cls.PRESET_BOOKSHELVES.values()])
        query = ("SELECT * from bookshelves_books WHERE "
                 "bookshelf_id=ANY('{" + bookshelf_ids + "}'::int[]) "
                 "AND username=$username")
        if bookshelf_id:
            data['bookshelf_id'] = bookshelf_id
            query += ' AND bookshelf_id=$bookshelf_id'
        query += ' LIMIT $limit OFFSET $offset'
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
    def add(cls, username, bookshelf_id, work_id, edition_id=None, upsert=False):
        """Adds a book with `work_id` to user's bookshelf designated by
        `bookshelf_id`"""
        oldb = db.get_db()
        work_id = int(work_id)
        edition_id = int(edition_id) if edition_id else None
        bookself_id = int(bookshelf_id)
        data = {'work_id': work_id, 'username': username, 'edition_id': edition_id}

        users_status = cls.get_users_read_status_of_work(username, work_id)
        if not users_status:
            return oldb.insert('bookshelves_books', username=username,
                               bookshelf_id=bookshelf_id,
                               work_id=work_id, edition_id=edition_id)
        else:
            return oldb.update('bookshelves_books', where="work_id=$work_id AND username=$username",
                               bookshelf_id=bookshelf_id, vars=data)

    @classmethod
    def remove(cls, username, work_id, bookshelf_id=None, edition_id=None):
        oldb = db.get_db()
        where = {
            'username': username,
            'work_id': int(work_id),
            'edition_id': int(edition_id) if edition_id else None
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
