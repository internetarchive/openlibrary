import pickle
import logging
import datetime
import urlparse
import urllib

import web
from celery.task.control import inspect 
from infogami.utils.view import render_template
from infogami import config
import psycopg2


logger = logging.getLogger("admin.tasks")

@web.memoize
def connect_to_taskdb():
    import celeryconfig
    return web.database(**celeryconfig.OL_RESULT_DB_PARAMETERS)


def unpack_result(task):
    try:
        d = pickle.loads(task.result)
        return dict(arguments = d.get('largs',"") + d.get('kargs',""),
                    command = d.get('command',""),
                    started_at = d.get('started_at',"TBD"),
                    result = d.get('result',""),
                    log = d.get('log',""))
    except Exception, e:
        return dict(arguments = "unknown",
                    command = "unknown",
                    started_at = "TBD",
                    result = "unknown",
                    log = "unknown",
                    error = True)


def massage_tombstones(dtasks):
    """Massages the database task tombstones into things that can be
    displayed by the /admin task templates"""
    if not dtasks:
        raise StopIteration()
    else:
        for task in dtasks:
            p = unpack_result(task)
            yield dict(uuid = task.task_id,
                       command = p.get('command',""),
                       arguments = p.get('arguments',""),
                       status = task.status,
                       finished_at = task.date_done,
                       started_at = p.get('started_at',""))


def massage_taskslists(atasks):
    """Massage the output of the celery inspector into a format that
    can be printed by our template"""
    def _start_time(task):
        try:
            return datetime.datetime.utcfromtimestamp(task['time_start'])
        except Exception:
            return ""
    if not atasks:
        raise StopIteration()
    for host,tasks in atasks.iteritems():
        for task in tasks:
            yield dict(uuid = task.get('id',""),
                       started_at = _start_time(task),
                       command = task.get('name'),
                       args = task.get('args',"") + task.get('kwargs',""),
                       host = host,
                       affected_docs = 'tbd')

class tasklist(object):
    def GET(self):
        try:
            db = connect_to_taskdb()
        except Exception, e:
            return "Error in connecting to tombstone database"
        try:
            i = web.input(finishedat_start="", finishedat_end = "", offset=0, limit = 20)
            finishedat_start = i['finishedat_start']
            finishedat_end = i['finishedat_end']
            offset = int(i['offset'])
            limit = int(i['limit'])
            clauses = []
            if finishedat_start:
                clauses.append("date_done >= '%s'"%datetime.datetime.strptime(finishedat_start,"%m/%d/%Y").isoformat())
            if finishedat_end:
                clauses.append("date_done <= '%s'"%datetime.datetime.strptime(finishedat_end,"%m/%d/%Y").isoformat())
            where = " AND ".join(clauses)
            if where:
                completed_tasks = massage_tombstones(db.select('celery_taskmeta', order = "date_done desc", where = where, limit=limit, offset = offset))
                ntasks = db.select('celery_taskmeta', where = where, what = "count(*)")[0].count
            else:
                completed_tasks = massage_tombstones(db.select('celery_taskmeta', order = "date_done desc",  limit=limit, offset = offset))
                ntasks = db.select('celery_taskmeta', what = "count(*)")[0].count
            task_ranges = range(0, ntasks, limit)
        except psycopg2.ProgrammingError, e:
            return "<p>The celery database has not been created. If this is the first time you're viewing this page, please refresh this page once celery completes a few tasks. The tombstone datbase will automatically be initialised</p>"
        inspector = inspect()
        active_tasks = massage_taskslists(inspector.active())
        reserved_tasks = massage_taskslists(inspector.reserved())
        url = "/admin/tasks?" + urllib.urlencode(dict(finishedat_start = finishedat_start,
                                                     finishedat_end = finishedat_end,
                                                     limit = limit))
        return render_template("admin/tasks/index", completed_tasks, active_tasks, reserved_tasks,  
                               limit = limit, offset = offset, fstart = finishedat_start, fend = finishedat_end, base_url = url, task_ranges = task_ranges)


class tasks(object):
    def GET(self, taskid):
        try:
            db = connect_to_taskdb()
            q = "SELECT * FROM celery_taskmeta WHERE task_id = $taskid"
            ret = db.query(q, vars= locals())
            if not ret:
                return "No such task"
            else:
                tsk = ret[0]
                res = unpack_result(tsk)
            return render_template("admin/tasks/task", tsk, res)
        except Exception:
            logger.warning("Problem while obtaining task information '%s'", taskid, exc_info = True)
            return "Error in obtaining task information"
                
            
