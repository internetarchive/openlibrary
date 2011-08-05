"""
Utilities that interface with celery for the openlibrary application.
"""

import json
import datetime
import logging
import StringIO
import traceback
import calendar


import web
import yaml

# from celery.task import task
from celery.task import task
from functools import wraps

import celeryconfig

from openlibrary.core import stats

@web.memoize
def setup_stats():
    c = yaml.load(open(celeryconfig.OL_CONFIG))
    stats.client = stats.create_stats_client(c)

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


def create_patched_delay(original_fn):
    """Returns a patched version of delay that we can use to
    monkeypatch the actual one"""
    # @wraps(original_fn.delay)
    def delay2(*largs, **kargs):
        t = calendar.timegm(datetime.datetime.utcnow().timetuple())
        celery_extra_info = dict(enqueue_time = t)
        kargs.update(celery_extra_info = celery_extra_info)
        return original_fn.original_delay(*largs, **kargs)
    return delay2

def oltask(fn):
    """Openlibrary specific decorator for celery tasks that records
    some extra information in the database which we use for
    tracking"""
    @wraps(fn)
    def wrapped(*largs, **kargs):
        setup_stats()
        global task_context
        celery_extra_info = kargs.pop("celery_extra_info",{})
        enqueue_time = celery_extra_info.get('enqueue_time',None)
        s = StringIO.StringIO()
        h = logging.StreamHandler(s)
        h.setFormatter(logging.Formatter("%(asctime)s [%(name)s] [%(levelname)s] %(message)s"))
        logging.root.addHandler(h)
        try:
            started_at = calendar.timegm(datetime.datetime.utcnow().timetuple())
            try:
                wait_time = started_at - enqueue_time
                stats.put("ol.celery.task_wait_time", wait_time * 1000)
                stats.put("ol.celery.%s_wait_time"%fn.__name__, wait_time * 1000)
            except:
                pass
            ret = fn(*largs, **kargs)
        except Exception,e:
            log = s.getvalue()
            tb = traceback.format_exc()
            d = dict(largs = json.dumps(largs),
                     kargs = json.dumps(kargs),
                     command = fn.__name__,
                     enqueued_at = enqueue_time,
                     started_at = started_at,
                     log = log,
                     traceback = tb,
                     result = None,
                     context = task_context)
            logging.root.removeHandler(h)
            try:
                end_time = calendar.timegm(datetime.datetime.utcnow().timetuple())
                run_time = end_time - started_at
                stats.put("ol.celery.task_run_time", run_time * 1000)
                stats.put("ol.celery.%s_run_time"%fn.__name__, run_time * 1000)
            except:
                pass
            raise ExceptionWrapper(e, d)
        log = s.getvalue()
        d = dict(largs = json.dumps(largs),
                 kargs = json.dumps(kargs),
                 command = fn.__name__,
                 enqueued_at = enqueue_time,
                 started_at = started_at,
                 log = log,
                 result = ret,
                 context = task_context)
        logging.root.removeHandler(h)
        task_context = {}
        try:
            end_time = calendar.timegm(datetime.datetime.utcnow().timetuple())
            run_time = end_time - started_at
            stats.put("task_run_time", run_time * 1000)
            stats.put("%s_run_time"%fn.__name__, run_time * 1000)
        except:
            pass
        return d
    retval = task(wrapped)
    patched_delay = create_patched_delay(retval)
    retval.original_delay = retval.delay
    retval.delay = patched_delay
    return retval
