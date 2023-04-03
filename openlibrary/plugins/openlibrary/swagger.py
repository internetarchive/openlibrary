from infogami.utils import delegate
from infogami.utils.view import render_template


def setup():
    pass


class swagger(delegate.page):
    path = "/swagger/docs"

    def GET(self):
        return render_template("swagger/swaggerui.html")
