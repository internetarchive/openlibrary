import datetime

import web
from celery.task.control import inspect 
from infogami.utils.view import render_template
from infogami import config

def massage_taskslists(atasks):
    """Massage the output of the celery inspector into a format that
    can be printed by our template"""
    def _start_time(task):
        try:
            return datetime.datetime.fromtimestamp(task['time_start'])
        except Exception:
            return ""
    for host,tasks in atasks.iteritems():
        for task in tasks:
            yield dict(uuid = task.get('id',""),
                       started_at = _start_time(task),
                       command = task.get('name'),
                       args = task.get('args',"") + task.get('kwargs',""),
                       host = host,
                       affected_docs = 'tbd')
                       



class monitor(object):
    def GET(self):
        try:
            db = web.database(dbn="postgres",  db=config.get('celery',{})["tombstone_db"])
            completed_tasks = db.select('celery_taskmeta')
            
            inspector = inspect()
            active_tasks = massage_taskslists(inspector.active())
            reserved_tasks = massage_taskslists(inspector.reserved())
            
            return render_template("admin/tasks/index", completed_tasks, active_tasks, reserved_tasks)
        except Exception, e:
            print e
            return "Error in connecting to tombstone database"

    
    

