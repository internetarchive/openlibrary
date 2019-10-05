
import web
import logging

from infogami.utils import delegate
from infogami.utils.view import render_template, public

logger = logging.getLogger("openlibrary.design")

class home(delegate.page):
    path = "/developers/design"

    def GET(self):
        template = render_template("design")
        template.v2 = True
        return template

def setup():
    pass
