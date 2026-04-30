from datetime import datetime
from hashlib import md5
from typing import Literal, NotRequired, TypedDict
from urllib.parse import parse_qs

import web
from infogami.utils.view import public, render_template
from pydantic import BaseModel

from openlibrary.accounts import get_current_user
from openlibrary.core import cache
from openlibrary.core.fulltext import fulltext_search_async
from openlibrary.core.lending import compose_ia_url, get_available_async
from openlibrary.core.vendors import (
    get_amazon_metadata,
    get_betterworldbooks_metadata,
)
from openlibrary.i18n import gettext as _
from openlibrary.plugins.openlibrary.code import is_bot
from openlibrary.plugins.openlibrary.lists import get_lists_async, get_user_lists
from openlibrary.plugins.upstream.utils import render_macro
from openlibrary.plugins.upstream.yearly_reading_goals import get_reading_goals
from openlibrary.plugins.worksearch.code import (
    compute_work_search_html_fields,
    run_solr_query_async,
    work_search_async,
)
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme
from openlibrary.plugins.worksearch.subjects import (
    date_range_to_publish_year_filter,
    get_subject_async,
)
from openlibrary.utils.async_utils import async_bridge
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

    def __init__(self, year: int):
        self.year = year

    def generate(self) -> dict:
        year = self.year or datetime.now().year
        goal = get_reading_goals(year=year)
        component = render_template("reading_goals/reading_goal_progress", [goal])

        return {"partials": str(component)}


class MyBooksDropperListsPartial:
    """Handler for the MyBooks dropper list component."""

    def generate(self) -> dict:
        user_lists = get_user_lists(None)

        dropper = render_template("lists/dropper_lists", user_lists)
        list_data = {
            list_data["key"]: {
                "members": list_data["list_items"],
                "listName": list_data["name"],
            }
            for list_data in user_lists
        }

        return {
            "dropper": str(dropper),
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

    def __init__(self, params: CarouselLoadMoreParams):
        self.params = params

    async def generate_async(self) -> dict:
        p = self.params

        # Do search
        search_results = await self._make_book_query(p)

        # Render cards
        cards = []
        for index, work in enumerate(search_results):
            lazy = index > self.MAX_VISIBLE_CARDS
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
                    p.layout,
                    key=p.key,
                )
            )

        return {"partials": [str(template) for template in cards]}

    async def _make_book_query(self, params: CarouselLoadMoreParams) -> list:
        if params.queryType == "SEARCH":
            return await self._do_search_query(params)
        if params.queryType == "BROWSE":
            return await self._do_browse_query(params)
        if params.queryType == "TRENDING":
            return self._do_trends_query(params)
        if params.queryType == "SUBJECTS":
            return await self._do_subjects_query(params)

        raise ValueError("Unknown query type")

    async def _do_search_query(self, params: CarouselLoadMoreParams) -> list:
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

    async def _do_browse_query(self, params: CarouselLoadMoreParams) -> list:
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

    def _do_trends_query(self, params: CarouselLoadMoreParams) -> list:
        return get_trending_books(minimum=3, limit=params.limit, page=params.page, sort_by_count=False)

    async def _do_subjects_query(self, params: CarouselLoadMoreParams) -> list:
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


class AffiliateLinksPartial:
    """Handler for affiliate links"""

    def __init__(self, data: dict):
        self.data = data

    async def generate_async(self) -> dict:
        args = self.data.get("args", [])

        if len(args) < 2:
            raise ValueError("Unexpected amount of arguments")

        title, opts = args[0], args[1]
        isbn = opts.get("isbn", "")

        bwb_metadata = None
        amz_metadata = None
        if not is_bot() and opts.get("prices") and isbn:
            bwb_metadata = await get_betterworldbooks_metadata(isbn)
            if not (bwb_metadata and bwb_metadata.get("market_price")):
                amz_metadata = get_amazon_metadata(isbn, resources="prices")

        macro = web.template.Template.globals["macros"].AffiliateLinks(
            title,
            opts,
            async_load=False,
            bwb_metadata=bwb_metadata,
            amz_metadata=amz_metadata,
        )
        return {"partials": str(macro)}


class SearchFacetsPartial:
    """Handler for search facets sidebar and "selected facets" affordances."""

    def __init__(self, data: dict, sfw: bool = False):
        self.sfw = sfw
        self.data = data
        user = get_current_user()
        self.show_merge_authors = user and (user.is_librarian() or user.is_super_librarian() or user.is_admin())

    async def generate_async(self) -> dict:
        path = self.data.get("path")
        query = self.data.get("query", "")
        parsed_qs = parse_qs(query.replace("?", ""))
        param = self.data.get("param", {})

        sort = None
        search_response = await run_solr_query_async(
            WorkSearchScheme(),
            param,
            rows=0,
            page=1,
            sort=sort,
            spellcheck_count=3,
            fields=compute_work_search_html_fields(sort, self.sfw),
            facet=True,
            highlight=False,
            request_label="BOOK_SEARCH_FACETS",
        )

        sidebar = render_template(
            "search/work_search_facets",
            param,
            facet_counts=search_response.facet_counts,
            async_load=False,
            path=path,
            query=parsed_qs,
            show_merge_authors=self.show_merge_authors,
        )

        active_facets = render_template(
            "search/work_search_selected_facets",
            param,
            search_response,
            param.get("q", ""),
            path=path,
            query=parsed_qs,
        )

        return {
            "sidebar": str(sidebar),
            "title": active_facets.title,
            "activeFacets": str(active_facets).strip(),
        }


class FullTextSuggestionsPartial:
    """Handler for rendering full-text search suggestions."""

    def __init__(self, query: str):
        self.query = query or ""
        self.has_error: bool = False

    async def generate_async(self) -> dict:
        query = self.query
        data = await fulltext_search_async(query)
        # Add caching headers only if there were no errors in the search results
        self.has_error = "error" in data
        hits = data.get("hits", [])
        if not hits["hits"]:
            macro = "<div></div>"
        else:
            macro = web.template.Template.globals["macros"].FulltextSearchSuggestion(query, data)
        return {"partials": str(macro)}


class BookPageListsPartial:
    """Handler for rendering the book page "Lists" section"""

    def __init__(self, workId: str, editionId: str):
        self.workId = workId
        self.editionId = editionId

    async def generate_async(self) -> dict:
        results: dict = {"partials": []}
        keys = [k for k in (self.workId, self.editionId) if k]

        # Do checks and render
        lists = await get_lists_async(keys)
        results["hasLists"] = bool(lists)

        if not lists:
            results["partials"].append(_("This work does not appear on any lists."))
        else:
            query = "seed_count:[2 TO *] seed:(%s)" % " OR ".join(f'"{k}"' for k in keys)
            all_url = "/search/lists?q=" + web.urlquote(query) + "&sort=last_modified"
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

    def __init__(self, params: LazyCarouselParams):
        self.params = params

    async def generate_async(self) -> dict:
        books = await gather_lazy_carousel_data_async(
            query=self.params.query,
            sort=self.params.sort,
            limit=self.params.limit,
            has_fulltext_only=self.params.has_fulltext_only,
            safe_mode=self.params.safe_mode,
        )
        macro = render_macro(
            "RawQueryCarousel",
            (  # args as a tuple - will be unpacked to positional params
                self.params.query,
            ),
            lazy=False,
            title=self.params.title,
            sort=self.params.sort,
            key=self.params.key,
            limit=self.params.limit,
            search=self.params.search,
            has_fulltext_only=self.params.has_fulltext_only,
            url=self.params.url,
            layout=self.params.layout,
            fallback=self.params.fallback,
            safe_mode=self.params.safe_mode,
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


gather_lazy_carousel_data = async_bridge.wrap(gather_lazy_carousel_data_async)

# Expose this publicly for the template
public(gather_lazy_carousel_data)


def setup():
    pass
