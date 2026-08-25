import asyncio
from time import time
from urllib.parse import urlencode

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
        selected_codes = [sel.code for sel in selected_languages]

        async def search_and_count():
            """The results page plus the "Readable Only" toggle's count. When
            the filter is off the count needs its own readable-scoped query —
            run it concurrently with the main search."""
            search_coro = fulltext_search_async(
                build_fulltext_query(query, languages=language_names, readable=readable),
                page=page,
                limit=RESULTS_PER_PAGE,
                # Aggregations feed the page's language facet sidebar.
                facets=True,
            )
            if readable:
                results = await search_coro
                count = results.get("hits", {}).get("total") if "error" not in results else None
                return results, count
            count_coro = fulltext_search_async(
                build_fulltext_query(query, languages=language_names, readable=True),
                limit=0,
                facets=False,
            )
            results, count_results = await asyncio.gather(search_coro, count_coro)
            count = count_results.get("hits", {}).get("total") if "error" not in count_results else None
            return results, count

        results, readable_count = async_bridge.run(search_and_count()) if query else ({}, None)
        search_time = time() - search_start

        def filter_url(languages=selected_codes, readable=readable):
            """/search/inside URL for the current query with a modified
            filter set — used by the template's chips and facet links."""
            params = [("q", query)]
            params += [("language", code) for code in languages]
            if readable:
                params.append(("readable", "true"))
            return "/search/inside?" + urlencode(params)

        def facet_url(bucket_key):
            """Add a language facet bucket (a languageSorter name) to the
            current selection, as its MARC code where one is known."""
            code = name_to_code.get(bucket_key.strip().casefold(), bucket_key)
            return filter_url(languages=[*selected_codes, code])

        return render_template(
            "search/inside.tmpl",
            query,
            results,
            search_time,
            page=page,
            results_per_page=RESULTS_PER_PAGE,
            selected_languages=selected_languages,
            readable=readable,
            readable_count=readable_count,
            filter_url=filter_url,
            facet_url=facet_url,
        )


def setup():
    """
    This is just here to make sure this file is imported.
    Simply defining the class above as a subclass of delegate.page is enough
    for it to be in effect.
    """
    pass
