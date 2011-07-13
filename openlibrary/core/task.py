"""
Utilities that interface with celery for the openlibrary application.
"""

import json
import datetime
import logging
import StringIO

# from celery.task import task
from celery.task import task
from functools import wraps


# class oltask(task):
#     def delay(self, *largs, **kargs):
#         super(oltask, self).delay(largs, kargs)
    

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
        ret = fn(*largs, **kargs)
        log = s.getvalue()
        d = dict(largs = json.dumps(largs),
                 kargs = json.dumps(kargs),
                 command = fn.__name__,
                 started_at = datetime.datetime.now(), # This is wrong. Needs to be in .delay
                 log = log,
                 result = ret)
        logging.root.removeHandler(h)
        return d
    return task(wrapped)
