"""Controller for /libraries.
"""
import web
from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core import inlibrary

class libraries(delegate.page):
    def GET(self):
        return render_template("libraries/index")
        
class locations(delegate.page):
    path = "/libraries/locations.txt"

    def GET(self):
        libraries = inlibrary.get_libraries()
        web.header("Content-Type", "text/plain")
        return delegate.RawText(render_template("libraries/locations", libraries))

def setup():
    pass