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

def process_task_row(task):
    """Makes some changes to the task row from couch so that the
    template can display it properly"""
    task.value['started_at'] = datetime.datetime.utcfromtimestamp(task.value['started_at'])
    task.value['finished_at'] = datetime.datetime.utcfromtimestamp(task.value['finished_at'])
    task.value["keys"] = task.value['context'].get("keys",[])
    return task.value

class tasklist(object):
    def GET(self):
        db = connect_to_taskdb()
        completed_tasks = (process_task_row(x) for x in db.view("history/by_key"))
        return render_template("admin/tasks/index", completed_tasks)

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
                
            
