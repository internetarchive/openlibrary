from time import time

import web

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core.fulltext import fulltext_search

RESULTS_PER_PAGE = 20


def build_fulltext_query(q: str, language: str = "") -> str:
    """Combine the user's query with a language facet filter.

    The FTS endpoint parses ``q`` as a Lucene query, so a facet filter is an
    ANDed field clause. The user query is parenthesized so its own OR/AND
    structure can't leak into the filter, and quotes are stripped from the
    facet value so it can't break out of its clause.

    >>> build_fulltext_query("moby dick")
    'moby dick'
    >>> build_fulltext_query("moby dick", "French")
    '(moby dick) AND languageSorter:"French"'
    >>> build_fulltext_query("whale", 'Fre"nch')
    '(whale) AND languageSorter:"French"'
    """
    if not language:
        return q
    safe_language = language.replace('"', "")
    return f'({q}) AND languageSorter:"{safe_language}"'


class search_inside(delegate.page):
    path = "/search/inside"

    def GET(self):
        search_start = time()  # should probably use a @timeit decorator
        i = web.input(q="", page=1, language="")
        query = i.q
        page = int(i.page)
        language = i.language.strip()
        results = fulltext_search(
            build_fulltext_query(query, language),
            page=page,
            limit=RESULTS_PER_PAGE,
            # Aggregations feed the page's language facet sidebar.
            facets=True,
        )
        search_time = time() - search_start

        return render_template(
            "search/inside.tmpl",
            query,
            results,
            search_time,
            page=page,
            results_per_page=RESULTS_PER_PAGE,
            selected_language=language,
        )


def setup():
    """
    This is just here to make sure this file is imported.
    Simply defining the class above as a subclass of delegate.page is enough
    for it to be in effect.
    """
    pass
