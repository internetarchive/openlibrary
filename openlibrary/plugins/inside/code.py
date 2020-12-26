from time import time

import json
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

        return render_template('search/inside.tmpl', query, results, search_time,
                               page=page, results_per_page=RESULTS_PER_PAGE)
        page.v2 = True  # page is mobile-first
        return page


class search_inside_json(delegate.page):
    path = "/search/inside"
    encoding = "json"

    def GET(self):
        i = web.input(q='', page=1, limit=RESULTS_PER_PAGE)
        limit = min(i.limit, RESULTS_PER_PAGE) if i.limit else RESULTS_PER_PAGE
        query = i.q
        page = int(i.page)
        results = fulltext_search(query, page=page, limit=limit, js=True)
        web.header('Content-Type', 'application/json')
        return delegate.RawText(json.dumps(results, indent=4))
