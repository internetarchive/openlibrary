from urllib.parse import urlencode

import web
from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary.core.fulltext import (
    fulltext_page,
    fulltext_search_async,
    is_auto_phrased_query,
    resolve_language,
)
from openlibrary.utils.async_utils import async_bridge

RESULTS_PER_PAGE = 20


def unphrased_query_url(query: str, language: tuple[str, str] | None, readable: bool) -> str:
    """Search URL that preserves filters but opts out of automatic phrasing."""
    params = [("q", query), ("phrase", "false")]
    if language:
        params.append(("language", language[0]))
    if readable:
        params.append(("readable", "true"))
    return f"/search/inside?{urlencode(params)}"


def empty_reason(query: str, rows: list, total: int, filtered: bool) -> str | None:
    """Why the page is empty, or None when it has rows.
    `total` counts hits the page never rendered, so an empty page always needs a reason.

    >>> empty_reason("dune", [], 0, filtered=False)
    'no_matches'
    >>> empty_reason("dune", [], 4312, filtered=True)
    'filtered_out'
    >>> empty_reason("dune", [], 4312, filtered=False)
    'past_end'
    >>> empty_reason("dune", ["row"], 4312, filtered=True) is None
    True
    >>> empty_reason("", [], 0, filtered=False) is None
    True
    """
    if not query or rows:
        return None
    if not total:
        return "no_matches"
    return "filtered_out" if filtered else "past_end"


class search_inside(delegate.page):
    path = "/search/inside"

    def GET(self):
        i = web.input(q="", page=1, language=[], readable="", phrase="true")
        query = i.q
        page = int(i.page)
        readable = i.readable == "true"
        phrase = i.phrase != "false"
        # (code, name): FTS takes the name; generated URLs keep the code.
        language = resolve_language(i.language)

        # Readable filters fetched hits, not `q` (see the `lang` note in fulltext_search_async).
        results = (
            async_bridge.run(
                fulltext_search_async(
                    query,
                    page=page,
                    limit=RESULTS_PER_PAGE,
                    facets=False,
                    readable=readable,
                    language=language[1] if language else None,
                    phrase=phrase,
                )
            )
            if query
            else {}
        )
        rows, total = fulltext_page(results)

        return render_template(
            "search/inside.tmpl",
            query,
            rows,
            total,
            page=page,
            results_per_page=RESULTS_PER_PAGE,
            language=language,
            readable=readable,
            phrase=phrase,
            was_auto_phrased=phrase and is_auto_phrased_query(query),
            unphrased_url=unphrased_query_url(query, language, readable),
            error=results.get("error"),
            empty_reason=empty_reason(query, rows, total, filtered=readable or bool(language)),
        )


def setup():
    """
    This is just here to make sure this file is imported.
    Simply defining the class above as a subclass of delegate.page is enough
    for it to be in effect.
    """
    pass
