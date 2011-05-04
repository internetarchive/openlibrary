from infogami.utils.view import render_template

from openlibrary.core import support

support_db = None

class cases(object):
    def GET(self):
        cases = support_db.get_all_cases()
        return render_template("admin/cases", cases)


def setup():
    global support_db
    support_db = support.Support()

