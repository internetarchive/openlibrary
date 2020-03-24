"""Interface to access the database of openlibrary.
"""
import web
from infogami.utils import stats

@web.memoize
def _get_db():
    return web.database(**web.config.db_parameters)

def get_db():
    """Returns an instance of webpy database object.

    The database object is cached so that one object is used everywhere.
    """
    return _get_db()

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
    f.__doc__ = "Equivalent to get_db().%s(*args, **kwargs).""" % method_name
    return f

query = _proxy("query")
select = _proxy("select")
where = _proxy("where")

insert = _proxy("insert")
update = _proxy("update")
delete = _proxy("delete")
transaction = _proxy("transaction")

