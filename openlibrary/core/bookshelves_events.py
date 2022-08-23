from datetime import date, datetime
from . import db


class BookshelvesEvents:

    TABLENAME = 'bookshelves_events'
    EVENT_TYPES = {
        'start': 1,
        'update': 2,
        'finish': 3,
    }

    # Create methods:
    @classmethod
    def create_event(
        cls, username, work_id, edition_id, event_date, event_type=EVENT_TYPES['start']
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
    def select_all_by_username(cls, username):
        # TODO: how should these be ordered?  edition_id and event_date?
        oldb = db.get_db()

        where_clause = 'username=$username'
        where_vars = {'username': username}
        return list(oldb.select(cls.TABLENAME, where=where_clause, vars=where_vars))

    @classmethod
    def select_by_id(cls, pid):
        oldb = db.get_db()

        return list(oldb.select(cls.TABLENAME, where='id=$id', vars={'id': pid}))

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
