"""Rendering of the search page's sidebar facets and selected-facet chips."""

from typing import NamedTuple

from infogami.utils.view import public

from openlibrary.core.helpers import commify
from openlibrary.core.jinja import get_jinja_env
from openlibrary.i18n import gettext as _
from openlibrary.plugins.openlibrary.code import changequery
from openlibrary.plugins.upstream.utils import get_language_name, json_encode
from openlibrary.plugins.worksearch.code import (
    SearchResponse,
    get_active_availability,
    get_availability_label,
    get_facet_map,
)
from openlibrary.utils.request_context import get_request_lang

# Search sidebar facets: how many entries each facet shows before "More", and
# how many more each click reveals. Read by hydrateFacets() in search.js from
# the sidebar's data-config attribute.
SEARCH_FACETS_CONFIG = {"start_facet_count": 5, "facet_inc": 10}

# data-ol-link-track labels of the sidebar facet chips, by facet header.
SEARCH_FACET_TRACK_NAMES = {
    "has_fulltext": "Ebook",
    "author_key": "Author",
    "subject_facet": "Subjects",
    "person_facet": "People",
    "place_facet": "Places",
    "time_facet": "Times",
    "first_publish_year": "FirstPublished",
    "publisher_facet": "Publisher",
    "language": "Language",
}


@public
def render_search_facets(
    param: dict,
    facet_counts: dict[str, list[tuple[str, str, int]]] | None = None,
    async_load: bool = True,
    path: str | None = None,
    query: dict | None = None,
    show_merge_authors: bool = False,
) -> str:
    """Render the search sidebar facets (search/work_search_facets.html.jinja).

    `async_load=True` renders "Loading..." placeholders that search.js replaces;
    with the real facet counts it renders the facet entries. `query` is the
    current query string as a dict (list values for repeated params).
    """
    query = query or {}

    def add_facet_url(k: str, v: str) -> str:
        if k != "has_fulltext":
            return changequery(query=dict(query), page=None, _path=path, **{k: param.get(k, []) + [v]})
        else:
            return changequery(query=dict(query), page=None, _path=path, **{k: v})

    def add_track(key: str) -> str:
        """KeyError will be raised if key is not in SEARCH_FACET_TRACK_NAMES."""
        return "SearchFacet|" + SEARCH_FACET_TRACK_NAMES[key]

    facets = []
    for header, label in get_facet_map():
        # has_fulltext and public_scan_b are owned by the filter row, not the sidebar.
        if header in ("has_fulltext", "public_scan_b"):
            continue
        counts: list[tuple] = [(None, None, None)] if async_load else [i for i in (facet_counts or {})[header] if i[0] not in param.get(header, [])]
        if len(counts) <= 1 and not async_load:
            continue
        facets.append((header, label, counts))

    template = get_jinja_env().get_template("search/work_search_facets.html.jinja")
    return template.render(
        facets=facets,
        async_load=async_load,
        show_merge_authors=show_merge_authors,
        start_facet_count=SEARCH_FACETS_CONFIG["start_facet_count"],
        add_facet_url=add_facet_url,
        add_track=add_track,
        commify=commify,
        config_json=json_encode(SEARCH_FACETS_CONFIG),
        param_json=json_encode(param),
        async_load_json=json_encode(async_load),
    )


class SelectedSearchFacets(NamedTuple):
    """Return type of render_selected_search_facets()."""

    html: str
    # The search page's document title (search.js assigns it to document.title),
    # or None when nothing is rendered: no search params, or a Solr error.
    title: str | None


@public
def render_selected_search_facets(
    param: dict,
    search_response: SearchResponse,
    q_param: str,
    path: str | None = None,
    query: dict | None = None,
) -> SelectedSearchFacets:
    """Render the "selected facets" chips (search/work_search_selected_facets.html.jinja)
    and build the search page's document title.
    """
    query = query or {}
    fulltext_names = {"true": "Ebooks", "false": "Exclude ebooks"}
    facet_map = get_facet_map()
    # get_language_name() needs the request's UI language to pick the
    # translated language name. Use get_request_lang() instead of get_lang(),
    # since this runs both on the web.py server (work_search.html) and on the
    # FastAPI partials endpoint, and FastAPI doesn't populate web.ctx.lang —
    # get_request_lang() reads the unified req_context.
    user_lang = get_request_lang()
    # Facets surfaced by the filter row rather than as chips here, mirroring the
    # header search modal: `has_fulltext` / `public_scan` / `print_disabled` by
    # the availability toggle, and `language` by the language popover. Excluded
    # from the facet_map chip loop below.
    special_handled = {"has_fulltext", "public_scan_b", "language"}

    def del_facet_url(k: str, v: str) -> str:
        if k != "has_fulltext":
            return changequery(page=None, _path=path, query=dict(query), **{k: [i for i in param.get(k, []) if i != v]})
        else:
            return changequery(page=None, _path=path, query=dict(query), **{k: None})

    active_availability = get_active_availability(param) if param else "all"
    selected_languages = list(param.get("language", [])) if param else []

    # Build the (header, value, display) tuples for the non-special facet chips
    # (subject_facet, author_key, etc.). For most facets the raw URL value is
    # already a usable display name, so we render the chip even when
    # facet_counts is empty (e.g. a zero-result search, or a value outside
    # Solr's facet.limit top-N). `author_key` is the exception: its raw value
    # is an OL ID like "OL12345A" — we keep gating it on facet_counts
    # resolving a display name rather than rendering the bare ID.
    def build_other_chips() -> list[tuple[str, str, str]]:
        if not param:
            return []
        facet_counts = search_response.facet_counts or {}
        chips = []
        for header, _label in facet_map:
            if header in special_handled:
                continue
            selected = param.get(header, [])
            if not selected:
                continue
            display_by_key = {k: d for k, d, _count in facet_counts.get(header, [])}
            for v in selected:
                if header == "author_key" and v not in display_by_key:
                    # Wait for the async sidebar request to resolve the name
                    # so we don't render the bare OL ID on the chip.
                    continue
                chips.append((header, v, display_by_key.get(v, v)))
        return chips

    other_chips = build_other_chips()
    show_chips_bar = bool(other_chips)

    title = None
    if param and not search_response.error:
        title_parts: list = []
        if q_param:
            title_parts.append(q_param)
        if active_availability != "all":
            title_parts.append(get_availability_label(active_availability))
        for lang_code in selected_languages:
            title_parts.append(get_language_name("/languages/" + lang_code, user_lang))
        title_parts.extend(chip_display for _header, _v, chip_display in other_chips)
        title = _("%(title)s - search", title=", ".join(title_parts))
    else:
        show_chips_bar = False

    template = get_jinja_env().get_template("search/work_search_selected_facets.html.jinja")
    html = template.render(
        show_chips_bar=show_chips_bar,
        other_chips=other_chips,
        del_facet_url=del_facet_url,
        fulltext_names=fulltext_names,
        active_availability=active_availability,
        param=param,
        search_response=search_response,
    )
    return SelectedSearchFacets(html=html, title=title)
