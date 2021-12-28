from infogami.utils import delegate
from infogami.utils.view import render_template


def setup():
    pass


class author(delegate.page):
    path = "/authors"

    def GET(self):
        return render_template("authors/index.html")

class dist(delegate.page):
    path = "/ap"

    def GET(self):
        return render_template("dist/index.html")

class swagger(delegate.page):
    path = "/api/docs1"

    def GET(self):
        return render_template("swagger/swaggerui.html")
