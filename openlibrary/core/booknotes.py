from openlibrary.utils.dateutil import DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO

from . import db
from .bookdb import BookDBModel


class Booknotes(BookDBModel):
    TABLENAME = "booknotes"
    PRIMARY_KEY = ("username", "work_id", "edition_id")
    NULL_EDITION_VALUE = -1
    ALLOW_DELETE_ON_CONFLICT = False

    @classmethod
    def summary(cls) -> dict:
        return {
            "total_notes_created": {
                "total": cls.total_count(),
                "month": cls.total_count(since=DATE_ONE_MONTH_AGO),
                "week": cls.total_count(since=DATE_ONE_WEEK_AGO),
            },
            "total_note_takers": {
                "total": cls.total_unique_users(),
                "month": cls.total_unique_users(since=DATE_ONE_MONTH_AGO),
                "week": cls.total_unique_users(since=DATE_ONE_WEEK_AGO),
            },
        }

    @classmethod
    def total_booknotes(cls, since=None) -> int:
        """Alias for total_count() — kept for backward compatibility."""
        return cls.total_count(since=since)

    @classmethod
    def most_notable_books(cls, limit=10, since=False):
        """Alias for most_popular() — kept for backward compatibility."""
        return cls.most_popular(limit=limit, since=since)

    @classmethod
    def get_booknotes_for_work(cls, work_id):
        oldb = db.get_db()
        query = "SELECT * from booknotes where work_id=$work_id"
        return list(oldb.query(query, vars={"work_id": work_id}))

    @classmethod
    def count_total_booksnotes_by_user(cls, username):
        """Counts the (int) total number of books logged by this `username`"""
        oldb = db.get_db()
        data = {"username": username}
        query = "SELECT count(*) from booknotes WHERE username=$username"
        return oldb.query(query, vars=data)[0]["count"]

    @classmethod
    def count_works_with_notes_by_user(cls, username):
        """
        Counts the total number of works logged by this 'username'
        """
        oldb = db.get_db()
        data = {"username": username}
        query = """
            SELECT
                COUNT(DISTINCT(work_id))
            FROM booknotes
            WHERE username=$username
        """
        return oldb.query(query, vars=data)[0]["count"]

    @classmethod
    def get_patron_booknote(cls, username, work_id, edition_id=NULL_EDITION_VALUE):
        note = cls.get_patron_booknotes(username, work_id=work_id, edition_id=edition_id)
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
            "username": username,
            "work_id": work_id,
            "edition_id": edition_id,
            "limit": limit,
            "offset": limit * (page - 1),
            "search": search,
        }
        query = "SELECT * from booknotes WHERE username=$username "
        if work_id:
            query += "AND work_id=$work_id AND edition_id=$edition_id "
        if search:
            data["search_pattern"] = f"%{search}%"
            query += "AND notes LIKE $search_pattern "
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
        data = {"username": username, "limit": limit, "offset": limit * (page - 1)}
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
        records = cls.get_patron_booknotes(username, work_id=work_id, edition_id=edition_id)
        if not records:
            return oldb.insert(
                "booknotes",
                username=username,
                work_id=work_id,
                notes=notes,
                edition_id=edition_id,
            )
        return oldb.update(
            "booknotes",
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
            "username": username,
            "work_id": int(work_id),
            "edition_id": edition_id,
        }
        try:
            return oldb.delete(
                "booknotes",
                where=("work_id=$work_id AND username=$username AND edition_id=$edition_id"),
                vars=where,
            )
        except:  # we want to catch no entry exists
            return None
