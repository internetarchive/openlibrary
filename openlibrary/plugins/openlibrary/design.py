import logging

import web
from infogami.utils import delegate
from infogami.utils.view import public, render_template

logger = logging.getLogger("openlibrary.design")


class home(delegate.page):
    path = "/developers/design"

    def GET(self):
        template = render_template("design")
        template.v2 = True
        return template


def setup():
    pass
