import datetime

import web
from celery.task.control import inspect 
from infogami.utils.view import render_template

def massage_taskslists(atasks):
    """Massage the output of the celery inspector into a format that
    can be printed by our template"""
    for host,tasks in atasks.iteritems():
        for task in tasks:
            print "Yielding   ", task
            yield dict(uuid = task['id'],
                       started_at = datetime.datetime.fromtimestamp(task['time_start']),
                       command = task['name'],
                       args = task['args'] + task['kwargs'],
                       host = host,
                       affected_docs = 'tbd')
                       



class monitor(object):
    def GET(self):
        db = web.database(dbn="postgres",  db="celery")
        completed_tasks = db.select('celery_taskmeta')
        
        inspector = inspect()
        active_tasks = massage_taskslists(inspector.active())

        return render_template("admin/tasks/index", completed_tasks, active_tasks)
    
    

