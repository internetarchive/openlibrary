from datetime import datetime
from enum import IntEnum, EnumMeta
from . import db


class BookshelfEventMeta(EnumMeta):
    def __contains__(cls, item):
        return item in cls.__members__.values()


class BookshelfEvent(IntEnum, metaclass=BookshelfEventMeta):
    START = 1
    UPDATE = 2
    FINISH = 3


class BookshelvesEvents(db.CommonExtras):

    TABLENAME = 'bookshelves_events'

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
            edition_id=edition_id,
            event_type=event_type,
            event_date=event_date,
        )

    # Read methods:
    @classmethod
    def select_by_id(cls, pid):
        oldb = db.get_db()

        return list(oldb.select(cls.TABLENAME, where='id=$id', vars={'id': pid}))

    @classmethod
    def get_latest_event_date(cls, username, work_id, edition_id, event_type):
        oldb = db.get_db()

        data = {
            'username': username,
            'work_id': work_id,
            'edition_id': edition_id,
            'event_type': event_type,
        }

        query = (
            f'SELECT id, event_date FROM {cls.TABLENAME}'
            ' WHERE username=$username AND work_id=$work_id'
            ' AND edition_id=$edition_id AND event_type=$event_type'
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

        return list(db.select(cls.TABLENAME, where=where, vars=data))

    @classmethod
    def exists(cls, pid) -> bool:
        return len(cls.select_by_id(pid)) > 0

    # Update methods:
    @classmethod
    def update_event(cls, pid, event_date=None, data=None):
        oldb = db.get_db()
        updates = {}
        if event_date:
            updates['event_date'] = event_date
        if data:
            updates['data'] = data
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
