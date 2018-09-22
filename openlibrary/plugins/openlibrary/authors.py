from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core import router

def setup():
    pass

class author(delegate.page):
    path = router.urls.authors.home

    def GET(self):
        return render_template("authors/index.html")

