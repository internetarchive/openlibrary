from datetime import date, datetime
from enum import IntEnum

from . import db


class BookshelfEvent(IntEnum):
    START = 1
    UPDATE = 2
    FINISH = 3

    @classmethod
    def has_value(cls, value: int) -> bool:
        return value in (item.value for item in BookshelfEvent.__members__.values())


class BookshelvesEvents(db.CommonExtras):
    TABLENAME = 'bookshelves_events'
    NULL_EDITION_ID = -1

    # Create methods:
    @classmethod
    def create_event(
        cls,
        username,
        work_id,
        edition_id,
        event_date,
        event_type=BookshelfEvent.START.value,
    ):
        oldb = db.get_db()

        return oldb.insert(
            cls.TABLENAME,
            username=username,
            work_id=work_id,
            edition_id=edition_id or cls.NULL_EDITION_ID,
            event_type=event_type,
            event_date=event_date,
        )

    # Read methods:
    @classmethod
    def select_by_id(cls, pid):
        oldb = db.get_db()

        return list(oldb.select(cls.TABLENAME, where='id=$id', vars={'id': pid}))

    @classmethod
    def get_latest_event_date(cls, username, work_id, event_type):
        oldb = db.get_db()

        data = {
            'username': username,
            'work_id': work_id,
            'event_type': event_type,
        }

        query = (
            f'SELECT id, event_date FROM {cls.TABLENAME}'
            ' WHERE username=$username AND work_id=$work_id'
            ' AND event_type=$event_type'
            ' ORDER BY event_date DESC LIMIT 1'
        )

        results = list(oldb.query(query, vars=data))
        return results[0] if results else None

    @classmethod
    def select_by_book_user_and_type(cls, username, work_id, edition_id, event_type):
        oldb = db.get_db()

        data = {
            'username': username,
            'work_id': work_id,
            'edition_id': edition_id,
            'event_type': event_type,
        }

        where = """
            username=$username AND
            work_id=$work_id AND
            edition_id=$edition_id AND
            event_type=$event_type
        """

        return list(oldb.select(cls.TABLENAME, where=where, vars=data))

    @classmethod
    def select_by_user_type_and_year(cls, username, event_type, year):
        oldb = db.get_db()

        data = {
            'username': username,
            'event_type': event_type,
            'event_date': f'{year}%',
        }

        where = """
            username=$username AND
            event_type=$event_type AND
            event_date LIKE $event_date
        """

        return list(oldb.select(cls.TABLENAME, where=where, vars=data))

    @classmethod
    def select_distinct_by_user_type_and_year(cls, username, event_type, year):
        """Returns a list of the most recent check-in events, with no repeating
        work IDs.  Useful for calculating one's yearly reading goal progress.
        """
        oldb = db.get_db()

        data = {
            'username': username,
            'event_type': event_type,
            'event_date': f'{year}%',
        }
        query = (
            f"select distinct on (work_id) work_id, * from {cls.TABLENAME} "
            "where username=$username and event_type=$event_type and "
            "event_date LIKE $event_date "
            "order by work_id, updated desc"
        )

        return list(oldb.query(query, vars=data))

    # Update methods:
    @classmethod
    def update_event(cls, pid, edition_id=None, event_date=None, data=None):
        oldb = db.get_db()
        updates = {}
        if event_date:
            updates['event_date'] = event_date
        if data:
            updates['data'] = data
        if edition_id:
            updates['edition_id'] = edition_id
        if updates:
            return oldb.update(
                cls.TABLENAME,
                where='id=$id',
                vars={'id': pid},
                updated=datetime.utcnow(),
                **updates,
            )
        return 0

    @classmethod
    def update_event_date(cls, pid, event_date):
        oldb = db.get_db()

        where_clause = 'id=$id'
        where_vars = {'id': pid}
        update_time = datetime.utcnow()

        return oldb.update(
            cls.TABLENAME,
            where=where_clause,
            vars=where_vars,
            updated=update_time,
            event_date=event_date,
        )

    def update_event_data(cls, pid, data):
        oldb = db.get_db()

        where_clause = 'id=$id'
        where_vars = {'id': pid}
        update_time = datetime.utcnow()

        return oldb.update(
            cls.TABLENAME,
            where=where_clause,
            vars=where_vars,
            updated=update_time,
            data=data,
        )

    # Delete methods:
    @classmethod
    def delete_by_id(cls, pid):
        oldb = db.get_db()

        where_clause = 'id=$id'
        where_vars = {'id': pid}

        return oldb.delete(cls.TABLENAME, where=where_clause, vars=where_vars)

    @classmethod
    def delete_by_username(cls, username):
        oldb = db.get_db()

        where_clause = 'username=$username'
        where_vars = {'username': username}

        return oldb.delete(cls.TABLENAME, where=where_clause, vars=where_vars)

    @classmethod
    def delete_by_username_and_work(cls, username, work_id):
        oldb = db.get_db()

        where_clause = 'username=$username AND work_id=$work_id'
        data = {
            'username': username,
            'work_id': work_id,
        }

        return oldb.delete(cls.TABLENAME, where=where_clause, vars=data)
