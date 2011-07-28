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



    def _get_tombstone(self, result, status, traceback):
        if status == "FAILURE":
            # Pull out traceback, args and other things from exception in case of FAILURE
            traceback = result.args[1].pop('traceback')
            result = result.args[1]
        doc = dict(status = str(status),
                   traceback = str(traceback))
        doc.update(result)
        return doc

    def _store_result(self, task_id, result, status, traceback=None):
        doc = self._get_tombstone(result, status, traceback)
        self.database[task_id] = doc
        self.database.save(doc)
        
        

        

