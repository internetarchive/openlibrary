import web

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import public, safeint, render


class bulk_search(delegate.page):
    path = "/search/bulk"

    def GET(self):
        i = web.input(q='')
        return render['bulk_search/demo'](q=i)


def setup():
    pass
