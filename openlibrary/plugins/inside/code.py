from time import time

import web

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core.fulltext import (
    build_fulltext_query,
    fulltext_search_async,
    language_name_maps,
)
from openlibrary.utils.async_utils import async_bridge

RESULTS_PER_PAGE = 20


class search_inside(delegate.page):
    path = "/search/inside"

    def GET(self):
        search_start = time()  # should probably use a @timeit decorator
        i = web.input(q="", page=1, language=[], readable="")
        query = i.q
        page = int(i.page)
        readable = i.readable == "true"

        # Language params may be MARC codes ("fre", the canonical form our own
        # URLs use) or languageSorter names ("French", from hand-edited URLs).
        # Resolve each to a (code, name) pair: the FTS query needs names, while
        # generated URLs stick to codes so the filter popover and the search
        # modal (both code-based) can read the selection back.
        code_to_name, name_to_code = language_name_maps()
        selected_languages = []
        for raw in i.language:
            lang = raw.strip()
            if not lang:
                continue
            code = name_to_code.get(lang.casefold(), lang.casefold())
            name = code_to_name.get(code, lang)
            if any(sel.name.casefold() == name.casefold() for sel in selected_languages):
                continue
            selected_languages.append(web.storage(code=code, name=name))
        language_names = [sel.name for sel in selected_languages]

        # Readability filters the fetched hits rather than the query: a readable
        # clause in `q` flips the FTS endpoint to its Lucene parser, which
        # ignores olonly=true and searches all of archive.org.
        results = (
            async_bridge.run(
                fulltext_search_async(
                    build_fulltext_query(query, languages=language_names),
                    page=page,
                    limit=RESULTS_PER_PAGE,
                    facets=False,
                    readable=readable,
                )
            )
            if query
            else {}
        )
        search_time = time() - search_start

        return render_template(
            "search/inside.tmpl",
            query,
            results,
            search_time,
            page=page,
            results_per_page=RESULTS_PER_PAGE,
            selected_languages=selected_languages,
            readable=readable,
        )


def setup():
    """
    This is just here to make sure this file is imported.
    Simply defining the class above as a subclass of delegate.page is enough
    for it to be in effect.
    """
    pass
