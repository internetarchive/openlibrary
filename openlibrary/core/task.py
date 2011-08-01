"""
Utilities that interface with celery for the openlibrary application.
"""

import json
import datetime
import logging
import StringIO
import traceback
import calendar

# from celery.task import task
from celery.task import task
from functools import wraps

class ExceptionWrapper(Exception):
    def __init__(self, exception, extra_info):
        self.exception = exception
        self.data = extra_info
        super(ExceptionWrapper, self).__init__(exception,  extra_info)
    

task_context = {}

def set_task_data(**kargs):
    "Sets a global task data that can be used in the the tombstone"
    global task_context
    task_context = kargs.copy()


def oltask(fn):
    """Openlibrary specific decorator for celery tasks that records
    some extra information in the database which we use for
    tracking"""
    @wraps(fn)
    def wrapped(*largs, **kargs):
        global task_context
        s = StringIO.StringIO()
        h = logging.StreamHandler(s)
        h.setFormatter(logging.Formatter("%(asctime)s [%(name)s] [%(levelname)s] %(message)s"))
        logging.root.addHandler(h)
        try:
            started_at = calendar.timegm(datetime.datetime.utcnow().timetuple())
            ret = fn(*largs, **kargs)
        except Exception,e:
            log = s.getvalue()
            tb = traceback.format_exc()
            d = dict(largs = json.dumps(largs),
                     kargs = json.dumps(kargs),
                     command = fn.__name__,
                     started_at = started_at,
                     log = log,
                     traceback = tb,
                     context = task_context)
            raise ExceptionWrapper(e, d)
        log = s.getvalue()
        d = dict(largs = json.dumps(largs),
                 kargs = json.dumps(kargs),
                 command = fn.__name__,
                 started_at = started_at,
                 log = log,
                 result = ret,
                 context = task_context)
        logging.root.removeHandler(h)
        task_context = {}
        return d
    return task(wrapped)
