from infogami.utils import delegate
from infogami.utils.view import render_template

class support(delegate.page):
    def GET(self):
        return render_template("support")

        


def setup():
    pass
