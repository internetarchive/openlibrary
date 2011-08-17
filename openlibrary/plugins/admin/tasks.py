import calendar
import pickle
import logging
import datetime
import urlparse
import urllib

import couchdb
from celery.task.control import inspect 
from infogami.utils.view import render_template
from infogami import config
import web


logger = logging.getLogger("admin.tasks")

@web.memoize
def connect_to_taskdb():
    db_uri = config.get("celery",{})["tombstone_db"]
    return couchdb.Database(db_uri)

def process_task_row(taskdoc):
    """Makes some changes to the task row from couch so that the
    template can display it properly"""
    taskdoc['started_at'] = datetime.datetime.utcfromtimestamp(taskdoc['started_at'])
    taskdoc['finished_at'] = datetime.datetime.utcfromtimestamp(taskdoc['finished_at'])
    try:
        taskdoc['enqueued_at'] = datetime.datetime.utcfromtimestamp(taskdoc['enqueued_at'])
    except:
        taskdoc['enqueued_at'] = taskdoc['started_at']
    taskdoc["keys"] = taskdoc['context'].get("keys",[])
    taskdoc["changeset"] = taskdoc['context'].get("changeset",None)
    return taskdoc

class tasklist(object):
    def GET(self):
        db = connect_to_taskdb()
        filters = web.input(command = None,
                            finishedat_start = None,
                            finishedat_end = None,
                            limit = 20,
                            offset = 0)
        command = filters["command"]
        limit = int(filters["limit"])
        offset = int(filters["offset"])
        if not command: 
            command = None # To make the view parameters work properly. otherwise, command becomes ''

        if filters["finishedat_start"]:
            finishedat_start = datetime.datetime.strptime(filters['finishedat_start'],"%Y-%m-%d %H:%M")
        else:
            finishedat_start = datetime.datetime(year = 2000, day = 1, month = 1)
            
        if filters["finishedat_end"]:
            finishedat_end = datetime.datetime.strptime(filters['finishedat_end'],"%Y-%m-%d %H:%M")
        else:
            finishedat_end = datetime.datetime.utcnow()
        
        finishedat_start = calendar.timegm(finishedat_start.timetuple())
        finishedat_end = calendar.timegm(finishedat_end.timetuple())

        completed_tasks = (process_task_row(x.doc) for x in db.view("history/tasks",
                                                                    startkey = [command,finishedat_end],
                                                                    endkey   = [command,finishedat_start],
                                                                    limit = limit,
                                                                    skip = offset,
                                                                    include_docs = True,
                                                                    descending = True,
                                                                    stale = "ok"))
        return render_template("admin/tasks/index", completed_tasks)

class tasks(object):
    def GET(self, taskid):
        try:
            db = connect_to_taskdb()
            try:
                task = db[taskid]
            except couchdb.http.ResourceNotFound:
                return "No such task"
            return render_template("admin/tasks/task", process_task_row(task))
        except Exception:
            logger.warning("Problem while obtaining task information '%s'", taskid, exc_info = True)
            return "Error in obtaining task information"
                
            
