import logging

from infogami.utils import delegate
from infogami.utils.view import render_template

logger = logging.getLogger("openlibrary.design")


class home(delegate.page):
    path = "/developers/design"

    def GET(self):
        return render_template("design")


def setup():
    pass
