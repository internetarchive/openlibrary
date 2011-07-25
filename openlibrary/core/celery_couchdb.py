from celery.backends.base import BaseDictBackend
from celery.exceptions import ImproperlyConfigured

class CouchDBBackend(BaseDictBackend): 
    def __init__(self, *largs, **kargs):
        print "Hello?"
        super(CouchDBBackend, self).__init__(**kargs)
        self.database = self.app.conf.CELERY_RESULT_DBURI
        if not self.database:
            raise ImproperlyConfigured(
                    "Missing connection string! Do you have "
                    "CELERY_RESULT_DBURI set to a real value?")
        
        
        
        

        

