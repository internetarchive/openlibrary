import web
from infogami.utils import delegate
from infogami.utils.view import render_template

class librarian_dashboard(delegate.page):
    path = '/librarians/dashboard'

    def GET(self):
        return render_template('librarians/dashboard')

def setup():
    pass