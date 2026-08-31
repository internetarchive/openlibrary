import web

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core.fulltext import (
    fulltext_page,
    fulltext_search_async,
    resolve_language,
)
from openlibrary.utils.async_utils import async_bridge

RESULTS_PER_PAGE = 20


def empty_reason(query: str, rows: list, total: int, filtered: bool) -> str | None:
    """Why this page has nothing to show, or None when it has rows.

    `total` counts matches the page never rendered — ones the readable filter
    dropped, or ones past the end of the result set — so an empty page always
    needs a reason of its own. Deciding here rather than in the template is what
    keeps the cases exhaustive: a count sitting above an empty list with no
    explanation is the failure mode.

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
        i = web.input(q="", page=1, language=[], readable="")
        query = i.q
        page = int(i.page)
        readable = i.readable == "true"
        # (code, name): the FTS query takes the name, generated URLs keep the
        # code so the filter popover and the search modal can read the selection
        # back. resolve_language is also where a multi-language request is
        # narrowed to the one the backend can apply.
        language = resolve_language(i.language)

        # Readability filters the fetched hits rather than the query: a readable
        # clause in `q` would flip the FTS endpoint to its Lucene parser, which
        # ignores olonly=true and searches all of archive.org.
        results = (
            async_bridge.run(
                fulltext_search_async(
                    query,
                    page=page,
                    limit=RESULTS_PER_PAGE,
                    facets=False,
                    readable=readable,
                    language=language[1] if language else None,
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
