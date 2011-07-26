"""
Utilities that interface with celery for the openlibrary application.
"""

import json
import datetime
import logging
import StringIO
import json
import traceback

# from celery.task import task
from celery.task import task
from functools import wraps

class ExceptionWrapper(Exception):
    def __init__(self, exception, extra_info):
        self.exception = exception
        self.data = extra_info
        super(ExceptionWrapper, self).__init__(exception,  extra_info)
    
    

def oltask(fn):
    """Openlibrary specific decorator for celery tasks that records
    some extra information in the database which we use for
    tracking"""
    @wraps(fn)
    def wrapped(*largs, **kargs):
        s = StringIO.StringIO()
        h = logging.StreamHandler(s)
        h.setFormatter(logging.Formatter("%(asctime)s [%(name)s] [%(levelname)s] %(message)s"))
        logging.root.addHandler(h)
        try:
            ret = fn(*largs, **kargs)
        except Exception,e:
            log = s.getvalue()
            tb = traceback.format_exc()
            d = dict(largs = json.dumps(largs),
                     kargs = json.dumps(kargs),
                     command = fn.__name__,
                     started_at = "TBD",
                     log = log,
                     traceback = tb)
            raise ExceptionWrapper(e, d)
        log = s.getvalue()
        d = dict(largs = json.dumps(largs),
                 kargs = json.dumps(kargs),
                 command = fn.__name__,
                 started_at = "TBD",
                 log = log,
                 result = ret)
        logging.root.removeHandler(h)
        return d
    return task(wrapped)
