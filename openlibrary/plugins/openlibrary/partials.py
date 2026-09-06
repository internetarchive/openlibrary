from dataclasses import dataclass
from hashlib import md5
from typing import Literal, NamedTuple, NotRequired, TypedDict
from urllib.parse import parse_qs, quote, quote_plus

import web
from pydantic import BaseModel

from infogami.utils.view import public, render_template
from openlibrary.accounts import get_current_user
from openlibrary.core import cache
from openlibrary.core.fulltext import fulltext_search_async
from openlibrary.core.helpers import affiliate_id, commify
from openlibrary.core.jinja import get_jinja_env
from openlibrary.core.lending import compose_ia_url, get_available_async
from openlibrary.core.vendors import (
    BetterWorldBooksMetadata,
    amazon_affiliate_url,
    get_amazon_metadata_async,
    get_betterworldbooks_metadata,
)
from openlibrary.i18n import gettext as _
from openlibrary.plugins.openlibrary.code import changequery, is_bot
from openlibrary.plugins.openlibrary.lists import get_lists_async, get_user_lists
from openlibrary.plugins.upstream.utils import get_language_name, json_encode, render_macro
from openlibrary.plugins.upstream.yearly_reading_goals import get_reading_goals
from openlibrary.plugins.worksearch.code import (
    SearchResponse,
    compute_work_search_html_fields,
    get_active_availability,
    get_availability_label,
    get_facet_map,
    run_solr_query_async,
    work_search_async,
)
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme
from openlibrary.plugins.worksearch.subjects import (
    date_range_to_publish_year_filter,
    get_subject_async,
)
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.request_context import get_request_lang
from openlibrary.views.loanstats import get_trending_books


def _solr_query_to_subject_key(query: str) -> str:
    """Convert Solr query format to subject key format."""
    # Handle Solr field format and seed format
    prefixes = [
        ("subject_key:", "/subjects/"),
        ("person_key:", "/subjects/person:"),
        ("place_key:", "/subjects/place:"),
        ("time_key:", "/subjects/time:"),
        ("subject:", "/subjects/"),
    ]

    for prefix, replacement in prefixes:
        if query.startswith(prefix):
            return f"{replacement}{query.removeprefix(prefix)}"

    # Already in correct format
    if query.startswith("/subjects/"):
        return query

    raise ValueError(f"Unable to convert query to subject key: {query}")


class ReadingGoalProgressPartial:
    """Handler for reading goal progress."""

    @classmethod
    def generate(cls, year: int) -> dict:
        goal = get_reading_goals(year=year)
        component = render_template("reading_goals/reading_goal_progress", [goal])

        return {"partials": str(component)}


class MyBooksDropperListsPartial:
    """Handler for the MyBooks dropper list component."""

    @classmethod
    def generate(cls) -> dict:
        user_lists = get_user_lists(None)

        template = get_jinja_env().get_template("lists/dropper_lists.html.jinja")
        dropper = template.render(lists=user_lists, json_encode=json_encode)
        list_data = {
            list_data["key"]: {
                "members": list_data["list_items"],
                "listName": list_data["name"],
            }
            for list_data in user_lists
        }

        return {
            "dropper": dropper,
            "listData": list_data,
        }


class CarouselLoadMoreParams(BaseModel):
    """Parameters for the carousel load-more partial."""

    queryType: Literal["SEARCH", "BROWSE", "TRENDING", "SUBJECTS"]
    q: str = ""
    limit: int = 18
    page: int = 1
    sorts: str = ""
    subject: str = ""
    hasFulltextOnly: bool = False
    key: str = ""
    layout: str | None = None
    published_in: str = ""


class CarouselCardPartial:
    """Handler for carousel "load_more" requests"""

    MAX_VISIBLE_CARDS = 5

    @classmethod
    async def generate_async(cls, params: CarouselLoadMoreParams) -> dict:
        # Do search
        search_results = await cls._make_book_query(params)

        # Render cards
        cards = []
        for index, work in enumerate(search_results):
            lazy = index > cls.MAX_VISIBLE_CARDS
            editions = work.get("editions", {})
            if not editions:
                book = work
            elif isinstance(editions, list):
                book = editions[0]
            else:
                book = editions.get("docs", [None])[0]
            book["authors"] = work.get("authors", [])

            cards.append(
                render_template(
                    "books/custom_carousel_card",
                    web.storage(book),
                    lazy,
                    params.layout,
                    key=params.key,
                )
            )

        return {"partials": [str(template) for template in cards]}

    @classmethod
    async def _make_book_query(cls, params: CarouselLoadMoreParams) -> list:
        if params.queryType == "SEARCH":
            return await cls._do_search_query(params)
        if params.queryType == "BROWSE":
            return await cls._do_browse_query(params)
        if params.queryType == "TRENDING":
            return await cls._do_trends_query(params)
        if params.queryType == "SUBJECTS":
            return await cls._do_subjects_query(params)

        raise ValueError("Unknown query type")

    @classmethod
    async def _do_search_query(cls, params: CarouselLoadMoreParams) -> list:
        fields = [
            "key",
            "title",
            "subtitle",
            "author_name",
            "cover_i",
            "ia",
            "availability",
            "id_project_gutenberg",
            "id_project_runeberg",
            "id_librivox",
            "id_standard_ebooks",
            "id_openstax",
            "editions",
        ]
        query_params: dict = {"q": params.q}
        if params.hasFulltextOnly:
            query_params["has_fulltext"] = "true"

        results = await work_search_async(
            query_params,
            sort=params.sorts or "new",
            fields=",".join(fields),
            limit=params.limit,
            facet=False,
            offset=params.page,
        )
        return results.get("docs", [])

    @classmethod
    async def _do_browse_query(cls, params: CarouselLoadMoreParams) -> list:
        url = compose_ia_url(
            query=params.q,
            limit=params.limit,
            page=params.page,
            subject=params.subject,
            sorts=params.sorts.split(",") if params.sorts else [],
            advanced=True,
            safe_mode=True,
        )
        results = await get_available_async(url=url)
        return results if "error" not in results else []

    @classmethod
    async def _do_trends_query(cls, params: CarouselLoadMoreParams) -> list:
        return await get_trending_books(minimum=3, limit=params.limit, page=params.page, sort_by_count=False)

    @classmethod
    async def _do_subjects_query(cls, params: CarouselLoadMoreParams) -> list:
        publish_year = date_range_to_publish_year_filter(params.published_in)
        subject_key = _solr_query_to_subject_key(params.q)
        # Convert page (1-indexed) to offset (0-indexed), ensure non-negative
        offset = max(0, params.page - 1) if params.page else 0
        subject = await get_subject_async(
            subject_key,
            offset=offset,
            limit=params.limit,
            publish_year=publish_year or None,
            request_label="BOOK_CAROUSEL",
        )
        return subject.get("works", [])


@dataclass(frozen=True, slots=True)
class AffiliateStoreBuildContext:
    title: str
    isbn: str | None
    asin: str | None
    bwb_metadata: BetterWorldBooksMetadata | None
    amz_metadata: dict | None


@dataclass(frozen=True, slots=True)
class AffiliateStore:
    key: str
    analytics_key: str
    name: str
    link: str
    price: str | None = None
    price_note: str = ""


def build_primary_stores(ctx: AffiliateStoreBuildContext) -> list[AffiliateStore]:
    """Build affiliate store data for rendering in AffiliateLinks.html."""

    bwb_link = f"https://www.betterworldbooks.com/search/results?q={quote_plus(ctx.title)}"
    if ctx.isbn:
        bwb_link = f"https://www.betterworldbooks.com/product/detail/{ctx.isbn}"

    bwb_market_price = ctx.bwb_metadata.get("market_price") if ctx.bwb_metadata else None
    bwb_price = ctx.bwb_metadata.get("price") if ctx.bwb_metadata else None
    amz_price = ctx.amz_metadata.get("price") if ctx.amz_metadata else None

    primary_stores: list[AffiliateStore] = [
        AffiliateStore(
            key="betterworldbooks",
            analytics_key="BetterWorldBooks",
            name=_("Better World Books"),
            link=bwb_link,
            price=bwb_price,
            price_note=_(" - includes shipping"),
        )
    ]

    if ctx.asin or ctx.isbn:
        amazon_link = amazon_affiliate_url(ctx.isbn, ctx.asin, affiliate_id("amazon"))
        if amazon_link:
            primary_stores.append(
                AffiliateStore(
                    key="amazon",
                    analytics_key="Amazon",
                    name=_("Amazon"),
                    link=amazon_link,
                    price=bwb_market_price or amz_price,
                )
            )

    return primary_stores


def build_more_stores(ctx: AffiliateStoreBuildContext) -> list[AffiliateStore]:
    """Build list of additional affiliate store data for rendering in AffiliateLinks.html."""
    if not ctx.isbn:
        return []

    return [
        AffiliateStore(
            key="bookshop-org",
            analytics_key="BookshopOrg",
            name=_("Bookshop.org"),
            link=f"https://bookshop.org/a/{affiliate_id('bookshop-org')}/{ctx.isbn}",
        ),
    ]


class AffiliateLinksPartial:
    """Handler for affiliate links"""

    @staticmethod
    async def generate_async(
        title: str,
        isbn: str | None,
        asin: str | None,
        prices: bool,
    ) -> dict:
        bwb_metadata = None
        amz_metadata = None
        should_fetch_prices = not is_bot() and prices
        if should_fetch_prices and isbn:
            bwb_metadata = await get_betterworldbooks_metadata(isbn)
            if not bwb_metadata or not bwb_metadata.get("market_price"):
                amz_metadata = await get_amazon_metadata_async(isbn, resources="prices")

        if bwb_metadata and "error" in bwb_metadata:
            bwb_metadata = None

        ctx = AffiliateStoreBuildContext(title, isbn, asin, bwb_metadata, amz_metadata)

        primary_stores = build_primary_stores(ctx)
        more_stores = build_more_stores(ctx)

        template = get_jinja_env().get_template("AffiliateLinks.html.jinja")
        html = template.render(primary_stores=primary_stores, more_stores=more_stores)

        return {"partials": html}


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

    Called from work_search.html with async_load=True ("Loading..." placeholders
    that search.js replaces) and from SearchFacetsPartial with the real facet
    counts. `query` is the current query string as a dict (list values for
    repeated params); add_facet_url() extends it with the clicked facet value.
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
        # Readability (has_fulltext) is owned by the "Readable Only" toggle in
        # the filter row now, so it's no longer offered as a sidebar facet.
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

    Called from work_search.html (`.html`) and from SearchFacetsPartial.
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
    # Availability and language are surfaced by the filter row (the toggle and
    # the language popover), mirroring the header search modal — they get no
    # chips here. Only the remaining facets (author, subject, year, …) do.
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


class SearchFacetsPartial:
    """Handler for search facets sidebar and "selected facets" affordances."""

    @classmethod
    async def generate_async(cls, data: dict, sfw: bool = False) -> dict:
        user = get_current_user()
        show_merge_authors = bool(user and user.is_librarian_or_higher())

        path = data.get("path")
        query = data.get("query", "")
        parsed_qs = parse_qs(query.replace("?", ""))
        param = data.get("param", {})

        sort = None
        search_response = await run_solr_query_async(
            WorkSearchScheme(),
            param,
            rows=0,
            page=1,
            sort=sort,
            spellcheck_count=3,
            fields=compute_work_search_html_fields(sort, sfw),
            facet=True,
            highlight=False,
            request_label="BOOK_SEARCH_FACETS",
        )

        sidebar = render_search_facets(
            param,
            facet_counts=search_response.facet_counts,
            async_load=False,
            path=path,
            query=parsed_qs,
            show_merge_authors=show_merge_authors,
        )

        active_facets = render_selected_search_facets(param, search_response, param.get("q", ""), path=path, query=parsed_qs)

        return {
            "sidebar": sidebar,
            # Plain text; search.js assigns it straight to document.title (#9787).
            "title": active_facets.title,
            "activeFacets": active_facets.html.strip(),
        }


class SubjectPublishingHistoryPartial:
    """Handler for the subject page's publishing-history chart."""

    @classmethod
    async def generate_async(cls, key: str) -> dict:
        subject = await get_subject_async(
            key,
            details=True,
            limit=0,
            facet_fields=[{"name": "publish_year", "limit": -1}],
            request_label="SUBJECT_PUBLISHING_HISTORY",
        )
        template = get_jinja_env().get_template("PublishingHistory.html.jinja")
        html = template.render(
            publishing_history_json=json_encode(subject.get("publishing_history", [])),
            async_load=False,
            key_json=json_encode(key),
        )
        return {"partials": html}


class SubjectRelatedPartial:
    """Handler for the subject page's related subjects/places/people/times widget."""

    @classmethod
    async def generate_async(cls, key: str) -> dict:
        subject = await get_subject_async(
            key,
            details=True,
            limit=0,
            facet_fields=["subject_facet", "person_facet", "place_facet", "time_facet"],
            request_label="SUBJECT_RELATED",
        )
        template = get_jinja_env().get_template("RelatedSubjects.html.jinja")
        html = template.render(page=subject, async_load=False, key=key)
        return {"partials": html}


@dataclass
class FullTextSuggestionsPartialResult:
    body: dict
    has_error: bool = False


class FullTextSuggestionsPartial:
    """Handler for rendering full-text search suggestions."""

    @classmethod
    async def generate_async(cls, query: str) -> FullTextSuggestionsPartialResult:
        data = await fulltext_search_async(query)
        hits = data.get("hits", {})
        if not hits.get("total"):
            macro = "<div></div>"
        else:
            macro = web.template.Template.globals["macros"].FulltextSearchSuggestion(query, data)
        return FullTextSuggestionsPartialResult(body={"partials": str(macro)}, has_error="error" in data)


class BookPageListsPartial:
    """Handler for rendering the book page "Lists" section"""

    @classmethod
    async def generate_async(cls, workId: str, editionId: str) -> dict:
        results: dict = {"partials": []}
        keys = [k for k in (workId, editionId) if k]

        # Do checks and render
        lists = await get_lists_async(keys)
        results["hasLists"] = bool(lists)

        if not lists:
            results["partials"].append(_("This work does not appear on any lists."))
        else:
            query = "seed_count:[2 TO *] seed:(%s)" % " OR ".join(f'"{k}"' for k in keys)
            all_url = "/search/lists?q=" + quote(query) + "&sort=last_modified"
            lists_template = render_template("lists/carousel", lists, all_url)
            results["partials"].append(str(lists_template))

        return results


class LazyCarouselParams(BaseModel):
    """Parameters for the lazy carousel partial."""

    query: str = ""
    title: str | None = None
    sort: str = "new"
    key: str = ""
    limit: int = 20
    search: bool = False
    has_fulltext_only: bool = True
    url: str | None = None
    layout: str = "carousel"
    fallback: str | None = None
    safe_mode: bool = True


class LazyCarouselPartial:
    """Handler for lazily-loaded query carousels."""

    @classmethod
    async def generate_async(cls, params: LazyCarouselParams) -> dict:
        books = await gather_lazy_carousel_data_async(
            query=params.query,
            sort=params.sort,
            limit=params.limit,
            has_fulltext_only=params.has_fulltext_only,
            safe_mode=params.safe_mode,
        )
        macro = render_macro(
            "RawQueryCarousel",
            (  # args as a tuple - will be unpacked to positional params
                params.query,
            ),
            lazy=False,
            title=params.title,
            sort=params.sort,
            key=params.key,
            limit=params.limit,
            search=params.search,
            has_fulltext_only=params.has_fulltext_only,
            url=params.url,
            layout=params.layout,
            fallback=params.fallback,
            safe_mode=params.safe_mode,
            books_data=books["docs"],
        )
        return {"partials": str(macro["__body__"])}


_CAROUSEL_FIELDS = [
    "key",
    "title",
    "subtitle",
    "editions",
    "author_name",
    "availability",
    "cover_i",
    "ia",
    "id_project_gutenberg",
    "id_librivox",
    "id_standard_ebooks",
    "id_openstax",
    "providers",
]

_SAFE_MODE_FILTER = '-subject:"content_warning:cover"'


class CarouselData(TypedDict):
    """Return type of gather_lazy_carousel_data."""

    docs: list[dict]
    error: NotRequired[bool]


@cache.memoize(
    engine="memcache",
    # TODO: move this into the cache decorator so it supports hashing like memcache_memoize does
    key=lambda query, sort, limit, has_fulltext_only, safe_mode: (
        "LazyCarouselData-" + md5(f"{query}-{sort}-{limit}-{has_fulltext_only}-{safe_mode}".encode()).hexdigest()
    ),
    expires=300,
    cacheable=lambda key, value: "error" not in value,
)
async def gather_lazy_carousel_data_async(
    query: str,
    sort: str,
    limit: int,
    has_fulltext_only: bool,
    safe_mode: bool,
) -> CarouselData:
    """Fetch carousel book data from Solr and return a typed dict with the docs.

    Extracted as a @public function so it can be called both from
    LazyCarouselPartial.generate() in the Python layer and directly from
    RawQueryCarousel.html when books_data is not pre-fetched.
    """
    if safe_mode and _SAFE_MODE_FILTER not in query:
        effective_query = f"{query} {_SAFE_MODE_FILTER}".strip()
    else:
        effective_query = query

    search_params: dict = {"q": effective_query}
    if has_fulltext_only:
        search_params["has_fulltext"] = "true"

    results = await work_search_async(
        search_params,
        sort=sort,
        fields=",".join(_CAROUSEL_FIELDS),
        limit=limit,
        facet=False,
        request_label="BOOK_CAROUSEL",
    )
    return_dict: CarouselData = {
        "docs": results.get("docs", []),
    }
    # Add error to make sure we don't cache
    if "error" in results:
        return_dict["error"] = results["error"]
    return return_dict


gather_lazy_carousel_data = async_bridge.wrap(gather_lazy_carousel_data_async, "gather_lazy_carousel_data")

# Expose this publicly for the template
public(gather_lazy_carousel_data)


def setup():
    pass
