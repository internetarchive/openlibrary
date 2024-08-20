import web

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import public, safeint, render


class bulk_search(delegate.page):
    path = "/search/bulk"

    def GET(self):
        return render['bulk_search/bulk_search']()


def setup():
    pass
