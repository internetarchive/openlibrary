from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.plugins.worksearch.code import random_author_search


def setup():
    pass


class author(delegate.page):
    path = "/authors"

    def GET(self):
        results = random_author_search()
        return render_template("authors/index.html", results)
