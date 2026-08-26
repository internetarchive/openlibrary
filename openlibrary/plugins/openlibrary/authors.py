from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.plugins.worksearch.code import random_author_search


def setup():
    pass


class author(delegate.page):
    path = "/authors"

    def GET(self):
        return render_template("authors/index.html", random_author_search())
