from . import db


class Booknotes(db.CommonExtras):

    TABLENAME = "booknotes"
    PRIMARY_KEY = ["username", "work_id", "edition_id"]
    NULL_EDITION_VALUE = -1
    ALLOW_DELETE_ON_CONFLICT = False

    @classmethod
    def total_booknotes(cls):
        oldb = db.get_db()
        query = f"SELECT count(*) from {cls.TABLENAME}"
        return oldb.query(query)['count']

    @classmethod
    def total_unique_users(cls, since=None):
        """Returns the total number of unique patrons who have made
        booknotes. `since` may be provided to only return the number of users after
        a certain datetime.date.

        XXX: This function is identical in all but docstring and db
        tablename from Bookshelves. This makes @mek think both classes
        could inherit a common BookDBModel class. Will try to keep
        this in mind and design accordingly
        """
        oldb = db.get_db()
        query = "select count(DISTINCT username) from booknotes"
        if since:
            query += " WHERE created >= $since"
        results = oldb.query(query, vars={'since': since})
        return results[0] if results else None

    @classmethod
    def most_notable_books(cls, limit=10, since=False):
        """Across all patrons"""
        oldb = db.get_db()
        query = "select work_id, count(*) as cnt from booknotes"
        if since:
            query += " AND created >= $since"
        query += ' group by work_id order by cnt desc limit $limit'
        return list(oldb.query(query, vars={'limit': limit, 'since': since}))

    @classmethod
    def get_booknotes_for_work(cls, work_id):
        oldb = db.get_db()
        query = "SELECT * from booknotes where work_id=$work_id"
        return list(oldb.query(query, vars={"work_id": work_id}))

    @classmethod
    def count_total_booksnotes_by_user(cls, username):
        """Counts the (int) total number of books logged by this `username`"""
        oldb = db.get_db()
        data = {'username': username}
        query = "SELECT count(*) from booknotes WHERE username=$username"
        return oldb.query(query, vars=data)[0]['count']

    @classmethod
    def count_works_with_notes_by_user(cls, username):
        """
        Counts the total number of works logged by this 'username'
        """
        oldb = db.get_db()
        data = {'username': username}
        query = """
            SELECT
                COUNT(DISTINCT(work_id))
            FROM booknotes
            WHERE username=$username
        """
        return oldb.query(query, vars=data)[0]['count']

    @classmethod
    def get_patron_booknote(cls, username, work_id, edition_id=NULL_EDITION_VALUE):
        note = cls.get_patron_booknotes(
            username, work_id=work_id, edition_id=edition_id
        )
        return note and note[0]

    @classmethod
    def get_patron_booknotes(
        cls,
        username,
        work_id=None,
        edition_id=NULL_EDITION_VALUE,
        search=None,
        limit=100,
        page=1,
    ):
        """By default, get all a patron's booknotes. if work_id, get book
        note for that work_id and edition_id.
        """
        oldb = db.get_db()
        page = int(page) if page else 1
        data = {
            'username': username,
            'work_id': work_id,
            'edition_id': edition_id,
            'limit': limit,
            'offset': limit * (page - 1),
            'search': search,
        }
        query = "SELECT * from booknotes WHERE username=$username "
        if work_id:
            query += "AND work_id=$work_id AND edition_id=$edition_id "
        if search:
            query += "AND notes LIKE '%$search%' "
        query += "LIMIT $limit OFFSET $offset"
        return list(oldb.query(query, vars=data))

    @classmethod
    def get_notes_grouped_by_work(cls, username, limit=25, page=1):
        """
        Returns a list of book notes records, which are grouped by work_id.
        The 'notes' field contains a JSON string consisting of 'edition_id'/
        book note key-value pairs.

        return: List of records grouped by works.
        """
        oldb = db.get_db()
        data = {'username': username, 'limit': limit, 'offset': limit * (page - 1)}
        query = """
            SELECT
                work_id,
                json_agg(row_to_json(
                    (SELECT r FROM (SELECT edition_id, notes) r)
                    )
                ) AS notes
            FROM booknotes
            WHERE username=$username
            GROUP BY work_id
            LIMIT $limit OFFSET $offset
        """

        return list(oldb.query(query, vars=data))

    @classmethod
    def add(cls, username, work_id, notes, edition_id=NULL_EDITION_VALUE):
        """Insert or update booknote. Create a new booknote if one doesn't
        exist, or gracefully update the record otherwise.

        return: the updates booknote record from the db.
        """
        oldb = db.get_db()
        data = {
            "work_id": work_id,
            "username": username,
            "notes": notes,
            "edition_id": edition_id,
        }
        records = cls.get_patron_booknotes(
            username, work_id=work_id, edition_id=edition_id
        )
        if not records:
            return oldb.insert(
                'booknotes',
                username=username,
                work_id=work_id,
                notes=notes,
                edition_id=edition_id,
            )
        return oldb.update(
            'booknotes',
            where="work_id=$work_id AND username=$username AND edition_id=$edition_id",
            notes=notes,
            edition_id=edition_id,
            vars=data,
        )

    @classmethod
    def remove(cls, username, work_id, edition_id=NULL_EDITION_VALUE):
        """Remove a patron's specific booknote by work_id.

        Technical note: work_id is not an optional argument and
        intentionally does not default to None (to reduce
        accidents/risk), however if one passes None as a value to
        work_id, this method will remove all booknotes for a patron
        (useful for a patron who may decide to close their account.

        Q: Is there a way to add a dryrun=False param to make this safer?

        return: a list of the IDs affected
        """
        oldb = db.get_db()
        where = {
            'username': username,
            'work_id': int(work_id),
            'edition_id': edition_id,
        }
        try:
            return oldb.delete(
                'booknotes',
                where=(
                    'work_id=$work_id AND username=$username AND edition_id=$edition_id'
                ),
                vars=where,
            )
        except:  # we want to catch no entry exists
            return None
