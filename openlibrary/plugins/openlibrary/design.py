
import web
import logging

from infogami.utils import delegate
from infogami.utils.view import render_template, public
from openlibrary.core import router

logger = logging.getLogger("openlibrary.design")

class home(delegate.page):
    path = router.urls.developers.design

    def GET(self):
        return render_template("design")

def setup():
    pass
