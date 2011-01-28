import os
import web

from infogami.utils.view import render_template
from openlibrary.core import admin

import utils

app = web.auto_application()
app.add_processor(utils.admin_processor)
app.notfound = utils.notfound

class home(app.page):
    path = "/admin/?"
    
    def GET(self):
        stats = admin.get_stats()
        return render_template("admin/index", stats)
        
class static(app.page):
    path = "(/(?:images|js|css)/.*)"
    
    def GET(self, path):
        raise web.seeother("/static/upstream" + path)

def setup():
    # load templates from this package so that they are available via render_template
    from infogami.utils import template
    template.load_templates(os.path.dirname(__file__))