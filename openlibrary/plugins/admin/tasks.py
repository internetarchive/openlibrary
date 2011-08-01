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
    taskdoc["keys"] = taskdoc['context'].get("keys",[])
    return taskdoc

class tasklist(object):
    def GET(self):
        db = connect_to_taskdb()
        completed_tasks = (process_task_row(x.doc) for x in db.view("history/tasks", include_docs = True))
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
                
            
