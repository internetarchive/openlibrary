"""Controller for home page.
"""
import web

from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary.core import admin

class home(delegate.page):
    path = "/"
    
    def is_enabled(self):
        return "lending_v2" in web.ctx.features
    
    def GET(self):
        stats = admin.get_stats()
        return render_template("home/index", stats)
    
def setup():
    pass