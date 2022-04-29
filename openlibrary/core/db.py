"""Interface to access the database of openlibrary.
"""
import web
from sqlite3 import IntegrityError
from psycopg2.errors import UniqueViolation
from infogami.utils import stats

@web.memoize
def _get_db():
    return web.database(**web.config.db_parameters)


def get_db():
    """Returns an instance of webpy database object.

    The database object is cached so that one object is used everywhere.
    """
    return _get_db()


class CommonExtras:
    """
    A set of methods used by bookshelves, booknotes, ratings, and observations tables
    """

    @classmethod
    def update_work_id(cls, current_work_id, new_work_id, _test=False):
        """This method allows all instances of a work_id (such as that of a
        redirect) to be updated to a new work_id.
        """
        oldb = get_db()
        t = oldb.transaction()
        rows_changed = 0
        rows_deleted = 0
        failed_deletes = 0

        try:
            rows_changed = oldb.update(
                cls.TABLENAME,
                where="work_id=$work_id",
                work_id=new_work_id,
                vars={"work_id": current_work_id})
        except (UniqueViolation, IntegrityError):
            (
                rows_changed,
                rows_deleted,
                failed_deletes,
            ) = cls.update_work_ids_individually(
                current_work_id, new_work_id, _test=_test
            )
        t.rollback() if _test else t.commit()
        return {
            'rows_changed': rows_changed,
            'rows_deleted': rows_deleted,
            'failed_deletes': failed_deletes,
        }

    @classmethod
    def update_work_ids_individually(cls, current_work_id, new_work_id, _test=False):
        oldb = get_db()
        rows_changed = 0
        rows_deleted = 0
        failed_deletes = 0

        # get records with old work_id
        # `list` used to solve sqlite cursor test
        rows = list(oldb.select(
            cls.TABLENAME,
            where="work_id=$work_id",
            vars={"work_id": current_work_id}))
        for row in rows:
            where = " AND ".join([
                f"{k}='{v}'"
                for k, v in row.items()
                if k in cls.PRIMARY_KEY
            ])
            try:
                # try to update the row to new_work_id
                t_update = oldb.transaction()
                oldb.query(f"UPDATE {cls.TABLENAME} set work_id={new_work_id} where {where}")
                rows_changed += 1
                t_update.rollback() if _test else t_update.commit()
            except (UniqueViolation, IntegrityError):
                t_delete = oldb.transaction()
                # otherwise, delete row with current_work_id if failed
                oldb.query(f"DELETE FROM {cls.TABLENAME} WHERE {where}")
                rows_deleted += 1
                if _test or not cls.ALLOW_DELETE_ON_CONFLICT:
                    t_delete.rollback()
                else:
                    t_delete.commit()

                if not cls.ALLOW_DELETE_ON_CONFLICT:
                    failed_deletes += 1
                    rows_deleted -= 1
        return rows_changed, rows_deleted, failed_deletes

    @classmethod
    def select_all_by_username(cls, username, _test=False):
        oldb = get_db()
        return list(oldb.select(
            cls.TABLENAME,
            where="username=$username",
            vars={"username": username}
        ))

    @classmethod
    def update_username(cls, username, new_username, _test=False):
        oldb = get_db()
        t = oldb.transaction()

        try:
            rows_changed = oldb.update(
                cls.TABLENAME,
                where="username=$username",
                username=new_username,
                vars={"username": username}
            )
        except (UniqueViolation, IntegrityError):
            # if any of the records would conflict with an exiting
            # record associated with new_username
            pass  # assuming impossible for now, not a great assumption

        t.rollback() if _test else t.commit()
        return rows_changed

    @classmethod
    def delete_all_by_username(cls, username, _test=False):
        oldb = get_db()
        t = oldb.transaction()

        try:
            rows_deleted = oldb.delete(
                cls.TABLENAME,
                where="username=$username",
                vars={"username": username}
            )
        except (UniqueViolation, IntegrityError):
            pass

        t.rollback() if _test else t.commit()
        return rows_deleted


def _proxy(method_name):
    """Create a new function that call method with given name on the
    database object.

    The new function also takes care of recording the stats about how
    long it took to execute this query etc.
    """

    def f(*args, **kwargs):
        stats.begin("db", method=method_name, args=list(args), kwargs=kwargs)
        m = getattr(get_db(), method_name)
        result = m(*args, **kwargs)
        stats.end()
        return result

    f.__name__ = method_name
    f.__doc__ = "Equivalent to get_db().%s(*args, **kwargs)." "" % method_name
    return f


query = _proxy("query")
select = _proxy("select")
where = _proxy("where")

insert = _proxy("insert")
update = _proxy("update")
delete = _proxy("delete")
transaction = _proxy("transaction")
