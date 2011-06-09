"""
Utilities that interface with celery for the openlibrary application.
"""

import json
import datetime

from celery.task import task
from functools import wraps


def oltask(fn):
    """Openlibrary specific decorator for celery tasks that records
    some extra information in the database which we use for
    tracking"""
    @wraps(fn)
    def wrapped(*largs, **kargs):
        ret = fn(*largs, **kargs)
        d = dict(largs = json.dumps(largs),
                 kargs = json.dumps(kargs),
                 command = fn.__name__,
                 started_at = datetime.datetime.now(),
                 result = ret)
        return d
    return task(wrapped)
