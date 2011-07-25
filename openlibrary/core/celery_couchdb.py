import json

from celery.backends.base import BaseDictBackend
from celery.exceptions import ImproperlyConfigured

try:
    import couchdb
except ImportError:
    couchdb = None


    


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
        try:
            serialised_result = json.dumps(result)
            doc = dict(result = serialised_result,
                       status = str(status),
                       traceback = str(traceback))
        except TypeError:
            serialised_result = str(result)
            doc = dict(result = None,
                       result_err = serialised_result,
                       status = str(status),
                       traceback = str(traceback))

        self.database[task_id] = doc
        self.database.save(doc)
        
        

        

