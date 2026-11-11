from math import ceil
from typing import TYPE_CHECKING, Any

import web
from markupsafe import Markup, escape

from infogami.utils import delegate
from infogami.utils.context import context
from infogami.utils.view import safeint
from openlibrary.accounts import get_current_user
from openlibrary.core.fulltext import (
    all_words_query,
    fulltext_page,
    fulltext_search_async,
    is_auto_phrased_query,
    phrase_query,
    resolve_language,
)
from openlibrary.core.helpers import commify
from openlibrary.core.jinja import render_jinja_template
from openlibrary.plugins.upstream.mybooks import get_reading_states
from openlibrary.plugins.upstream.utils import render_macro
from openlibrary.utils.async_utils import async_bridge

if TYPE_CHECKING:
    from openlibrary.core.fulltext import FulltextRow
    from openlibrary.fastapi.search import InsideNav, SearchNav

RESULTS_PER_PAGE = 20


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


def render_hit_rows(rows: list[FulltextRow], phrase: str, user: Any | None) -> list[Markup]:
    """Render one search row per hit, in one round of reading-state queries.

    `SearchResultsWork` is still Templetor (8 other callers, each with its own
    request state), so it renders here as a bridge, as /search's full text band
    does (`partials.render_fulltext_suggestion_row`). `reading_states` is passed
    in so the shelf button shows this reader's state rather than looking up its
    own, per row.
    """
    reading_states = get_reading_states(user, [row.edition for row in rows if row.edition])
    rendered = []
    for seq_index, row in enumerate(rows):
        if row.edition:
            macro = render_macro(
                "SearchResultsWork",
                (row.edition,),
                availability=row.availability,
                extra_row=render_jinja_template("FulltextSnippet.html.jinja", row=row, phrase=phrase),
                include_dropper=True,
                reading_states=reading_states,
                seq_index=seq_index,
                show_title_year=True,
            )
            rendered.append(Markup(str(macro["__body__"])))
        else:
            rendered.append(Markup(render_jinja_template("FulltextResultIA.html.jinja", row=row, phrase=phrase)))
    return rendered


def render_inside_body(
    *,
    nav: SearchNav,
    inside_nav: InsideNav,
    query: str,
    page: int,
    language: tuple[str, str] | None,
    readable: bool,
    phrase: bool,
    data: dict,
    user: Any | None,
) -> str:
    """Render /search/inside's page body from an FTS response, for either server.

    `phrase` is what the request asked for; a query that fell back to its loose
    words renders as all-words, and its snippets search for those words.
    """
    rows, total = fulltext_page(data)
    used_fallback = bool(data.get("all_words_fallback"))
    page_phrase = phrase and not used_fallback
    snippet_phrase = phrase_query(query) if page_phrase else all_words_query(query)

    return render_jinja_template(
        "search/inside.html.jinja",
        nav=nav,
        inside_nav=inside_nav,
        q=query,
        page=page,
        results_per_page=RESULTS_PER_PAGE,
        rows=render_hit_rows(rows, snippet_phrase, user) if rows else [],
        total=total,
        commified_total=commify(total),
        range_start=(page - 1) * RESULTS_PER_PAGE + 1,
        total_pages=ceil(total / RESULTS_PER_PAGE),
        language=language,
        readable=readable,
        was_auto_phrased=phrase and not used_fallback and is_auto_phrased_query(query),
        used_fallback=used_fallback,
        opted_out=not phrase and is_auto_phrased_query(query),
        error=data.get("error"),
        empty_reason=empty_reason(query, rows, total, filtered=readable or bool(language)),
    )


class search_inside(delegate.page):
    """Retire once production routes /search/inside to FastAPI (``openlibrary/fastapi/search.py``)."""

    path = "/search/inside"

    def GET(self):
        i = web.input(q="", page=1, language=[], readable="", phrase="true")
        query = i.q
        page = max(1, safeint(i.page, 1))
        readable = i.readable == "true"
        phrase = i.phrase != "false"
        # (code, name): FTS takes the name; generated URLs keep the code.
        language = resolve_language(i.language) if i.language else None

        # Readable filters fetched hits, not `q` (see the `lang` note in fulltext_search_async).
        data = (
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

        # Local imports: openlibrary.fastapi.search imports this module, and this handler is temporary.
        from openlibrary.fastapi.search import InsideNav, SearchNav, inside_search_title

        body = render_inside_body(
            nav=SearchNav.from_query(web.ctx.path, web.input(_method="get")),
            inside_nav=InsideNav.from_query(web.ctx.path, web.ctx.query),
            query=query,
            page=page,
            language=language,
            readable=readable,
            phrase=phrase,
            data=data,
            user=get_current_user(),
        )
        context.setdefault("bodyclass", []).append("search-page")
        # web.py's layout reads the title off the result, already escaped, as from Templetor's $var.
        return web.template.TemplateResult(__body__=body, title=escape(inside_search_title(query)))


def setup():
    """
    This is just here to make sure this file is imported.
    Simply defining the class above as a subclass of delegate.page is enough
    for it to be in effect.
    """
    pass
