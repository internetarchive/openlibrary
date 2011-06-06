import web
from infogami.utils.view import render_template

class monitor(object):
    def GET(self):
        db = web.database(dbn="postgres",  db="celery")
        completed_tasks = db.select('celery_taskmeta')
        return render_template("admin/tasks/index", completed_tasks)
    
    

