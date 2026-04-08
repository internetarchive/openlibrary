from time import time

import web

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core.fulltext import fulltext_search

RESULTS_PER_PAGE = 20


class search_inside(delegate.page):
    path = '/search/inside'

    def GET(self):
        search_start = time()  # should probably use a @timeit decorator
        i = web.input(q='', page=1)
        query = i.q
        page = int(i.page)
        results = fulltext_search(query, page=page, limit=RESULTS_PER_PAGE)
        search_time = time() - search_start

        return render_template(
            'search/inside.tmpl',
            query,
            results,
            search_time,
            page=page,
            results_per_page=RESULTS_PER_PAGE,
        )


def setup():
    """
    This is just here to make sure this file is imported.
    Simply defining the class above as a subclass of delegate.page is enough
    for it to be in effect.
    """
    pass
