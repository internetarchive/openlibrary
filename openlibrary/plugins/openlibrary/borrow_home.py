"""Controller for /borrow page.
"""
import web
from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.plugins.worksearch import code as worksearch

class borrow(delegate.page):
    path = "/borrow"
    
    def is_enabled(self):
        return "inlibrary" in web.ctx.features
    
    def GET(self):
        subject = worksearch.get_subject("/subjects/lending_library", details=True)
        return render_template("borrow/index", subject)

def setup():
    pass
    
    