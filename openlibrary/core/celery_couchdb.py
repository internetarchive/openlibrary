import json

from celery.backends.base import BaseDictBackend
from celery.exceptions import ImproperlyConfigured

try:
    import couchdb
except ImportError:
    couchdb = None


def maybe_serialise(data):
    """Tries to serialise the data into a JSON string. If it fails, it
    simply returns the str() representation"""
    try:
        return json.dumps(data)
    except TypeError:
        return str(data)
    


class CouchDBBackend(BaseDictBackend): 
    def __init__(self, *largs, **kargs):
        super(CouchDBBackend, self).__init__(**kargs)
        self.dburi = self.app.conf.CELERY_RESULT_DBURI
        if not self.dburi:
            raise ImproperlyConfigured(
                    "Missing connection string! Do you have "
                    "CELERY_RESULT_DBURI set to a real value?")

        if not couchdb:
            raise ImproperlyConfigured(
                "You need to install the couchdb library to use the "
                "CouchDB backend.")

        self.database = couchdb.Database(self.dburi)
        

    def _store_result(self, task_id, result, status, traceback=None):
        doc = dict(result = maybe_serialise(result),
                   status = maybe_serialise(status),
                   traceback = maybe_serialise(traceback))

        self.database[task_id] = doc
        self.database.save(doc)
        
        

        

