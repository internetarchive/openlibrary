from infogami.utils import delegate
from infogami.utils.view import render


class bulk_search(delegate.page):
    path = "/search/bulk"

    def GET(self):
        return render['bulk_search/bulk_search']()


def setup():
    pass
