from __future__ import annotations

from dataclasses import dataclass
from hashlib import md5
from typing import TYPE_CHECKING, Any, Literal, NotRequired, TypedDict, Unpack
from urllib.parse import parse_qs, quote, quote_plus

import web
from markupsafe import Markup
from pydantic import BaseModel

from infogami.utils.view import public
from openlibrary.core import cache
from openlibrary.core.follows import PubSub
from openlibrary.core.fulltext import fulltext_search_async
from openlibrary.core.helpers import affiliate_id, datestr, datetimestr_utc
from openlibrary.core.jinja import get_jinja_env, render_jinja_template
from openlibrary.core.lending import compose_ia_url, get_available_async
from openlibrary.core.vendors import (
    BetterWorldBooksMetadata,
    amazon_affiliate_url,
    get_amazon_metadata_async,
    get_betterworldbooks_metadata,
)
from openlibrary.i18n import gettext as _
from openlibrary.plugins.openlibrary.code import is_bot
from openlibrary.plugins.openlibrary.lists import (
    convert_list,
    get_lists_async,
    get_user_lists,
)
from openlibrary.plugins.upstream.borrow import datetime_from_isoformat
from openlibrary.plugins.upstream.utils import (
    get_user_object,
    json_encode,
    render_macro,
    urlencode,
)
from openlibrary.plugins.upstream.yearly_reading_goals import get_reading_goals
from openlibrary.plugins.worksearch.code import (
    compute_work_search_html_fields,
    run_solr_query_async,
    work_search_async,
)
from openlibrary.plugins.worksearch.facets import (
    render_search_facets,
    render_selected_search_facets,
)
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme
from openlibrary.plugins.worksearch.subjects import (
    date_range_to_publish_year_filter,
    get_subject_async,
)
from openlibrary.views.loanstats import get_trending_books

if TYPE_CHECKING:
    from openlibrary.fastapi.auth import AuthenticatedUser


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
        entries = [goal] if goal else []
        component = render_jinja_template("reading_goals/reading_goal_progress.html.jinja", entries=entries)
        return {"partials": component}


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


_CAROUSEL_CARD_FALLBACK_COVER = "https://openlibrary.org/static/images/icons/avatar_book.png"
# NOTE: Hard-coded to keep behavior unchanged during Templetor to Jinja conversion
# (PR 13578, issue 13570). Source template `books/custom_carousel_card.html:4`
# used `cover_host = '//covers.openlibrary.org'`. This keeps the DOM identical.
# Consider to use `get_coverstore_public_url()` in a follow-up change.
_CAROUSEL_CARD_COVER_HOST = "//covers.openlibrary.org"


def _resolve_carousel_card_cover_url(book) -> str | Literal[False]:
    """Resolve the cover image URL for a book. Serves both a Thing (with
    ``get_cover_url``) and a plain dict/Solr-doc shape."""
    if hasattr(book, "get_cover_url") and book.get_cover_url("M"):
        return book.get_cover_url("M")
    if book.get("cover_url"):
        return book.get("cover_url")
    cover_id = book.get("cover_id") or book.get("cover_i") or (book.get("covers") and book["covers"][0])
    if cover_id and cover_id != -1:
        return f"{_CAROUSEL_CARD_COVER_HOST}/b/id/{cover_id}-M.jpg"
    if book.get("ia"):
        return f"{_CAROUSEL_CARD_COVER_HOST}/b/ia/{book.get('ia')[0]}-M.jpg?default={_CAROUSEL_CARD_FALLBACK_COVER}"
    if book.get("ocaid"):
        return f"{_CAROUSEL_CARD_COVER_HOST}/b/ia/{book.get('ocaid')}-M.jpg?default={_CAROUSEL_CARD_FALLBACK_COVER}"
    if book.get("cover_edition_key"):
        return f"{_CAROUSEL_CARD_COVER_HOST}/b/olid/{book.get('cover_edition_key')}-M.jpg"
    return False


def _resolve_carousel_card_author_names(book) -> list[str]:
    """Serves both a Thing (list of author Things with a .name) and a plain
    dict/Solr-doc shape (author_name: list[str])."""
    if book.get("authors"):
        return [author.name or _("name missing") for author in book.authors]
    if book.get("author_name"):
        return book.get("author_name", [])
    return []


def _render_carousel_card_loan_status(book, *, work_key: str, secondary_action: bool, key: str) -> Markup:
    """Bridge call into the still-Templetor LoanStatus macro (183 lines, 8
    other callers; out of scope for this conversion per issue #13570).
    TODO: Convert LoanStatus to jinja and remove this bridge.
    """
    macro = render_macro(
        "LoanStatus",
        (book,),
        work_key=work_key,
        listen=False,
        secondary_action=secondary_action,
        analytics_override="BookCarousel|{action}Click|%s" % key,
    )
    return Markup(str(macro["__body__"]))


class CarouselCardData(TypedDict):
    url: str
    title: str
    byline: str
    author_names: list[str]
    cover_url: str | Literal[False]
    loan: dict[str, Any] | None
    expiry_utc: str
    expiry_display: str
    is_bookreader: bool
    waitlist_size: int
    key: str
    lazy: bool
    layout: str | None
    loan_status_html: Markup
    return_confirm_i18n: str
    request_fullpath: str


@public
def get_carousel_card_data(book, lazy: bool, layout: str | None, key: str, full_path: str, secondary_action: bool = False) -> CarouselCardData:
    """Gather data for books/custom_carousel_card.html.jinja.

    Like ReadingGoalProgressPartial.generate: Python gathers (hasattr/DB),
    Jinja only renders. No HTML is built here except loan_status_html which
    bridges the still-Templetor LoanStatus.
    """

    url = book.get("key") or book.url
    title = book.get("title", "")
    author_names = _resolve_carousel_card_author_names(book)
    byline = _(" by %(name)s", name=", ".join(author_names)) if author_names else ""

    loan = book.get("loan")
    waitlist_size = 0
    if loan and hasattr(book, "get_waitinglist_size"):
        waitlist_size = book.get_waitinglist_size()

    expiry = loan.get("expiry") if loan else None
    if expiry:
        expiry_dt = datetime_from_isoformat(expiry)
        expiry_utc = datetimestr_utc(expiry_dt)
        expiry_display = datestr(expiry_dt)
    else:
        expiry_utc = ""
        expiry_display = ""

    return {
        "url": url,
        "title": title,
        "byline": byline,
        "author_names": author_names,
        "cover_url": _resolve_carousel_card_cover_url(book),
        "loan": loan,
        "expiry_utc": expiry_utc,
        "expiry_display": expiry_display,
        "is_bookreader": bool(loan and loan.get("resource_type") == "bookreader"),
        "waitlist_size": waitlist_size,
        "key": key,
        "lazy": lazy,
        "layout": layout,
        "loan_status_html": _render_carousel_card_loan_status(book, work_key=url, secondary_action=(secondary_action and not loan), key=key),
        "return_confirm_i18n": json_encode({"confirm_return": _("Really return this book?")}),
        "request_fullpath": full_path,
    }


class CarouselCardPartial:
    """Handler for carousel "load_more" requests"""

    MAX_VISIBLE_CARDS = 5

    @classmethod
    async def generate_async(cls, params: CarouselLoadMoreParams, full_path: str) -> dict:
        # Do search
        search_results = await cls._make_book_query(params)

        # Render cards — gather data in Python, render in Jinja (like ReadingGoalProgressPartial)
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
            book = web.storage(book)

            try:
                data = get_carousel_card_data(book, lazy, params.layout, params.key, full_path)
                cards.append(render_jinja_template("books/custom_carousel_card.html.jinja", **data))
            except Exception:  # noqa: BLE001  # per-card isolation: one bad card should not break whole carousel
                continue

        return {"partials": cards}

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


class SearchFacetsPartial:
    """Handler for search facets sidebar and "selected facets" affordances."""

    @classmethod
    async def generate_async(cls, data: dict, sfw: bool = False, show_merge_authors: bool = False) -> dict:

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


class BookPageListCard(TypedDict):
    """Data for one Lists carousel card."""

    url: str
    showcase: dict[str, Any]
    owner: Any | None
    own_list: bool
    is_public: bool
    is_subscribed: int


class BookPageListsPartial:
    """Renders the Lists section on a book page."""

    LIMIT = 5
    RENDER_FALLBACK = "Unable to render this page."

    @classmethod
    def get_list_card(cls, lst: Any, user: AuthenticatedUser | None) -> BookPageListCard:
        """Build data for one card. Keep DB calls out of the template.

        ``lst`` is a web.storage from get_lists_async. Reload the full List
        for get_url and get_patron_showcase. The public_readlog check matches
        the old Templetor code. is_subscribed uses the same PubSub check as
        User.is_subscribed_user.
        """
        own_list = bool(user and lst.owner and lst.owner.key == user.user_key)
        converted = convert_list(lst.key)
        card: BookPageListCard = {
            "url": converted.get_url(),
            "showcase": converted.get_patron_showcase(),
            "owner": lst.owner,
            "own_list": own_list,
            "is_public": False,
            "is_subscribed": 0,
        }
        if lst.owner and not own_list:
            owner_username = lst.owner.key.split("/")[-1]
            owner_account = get_user_object(owner_username)
            settings = owner_account.get_users_settings()
            card["is_public"] = bool(settings and settings.get("public_readlog", "no") == "yes")
            card["is_subscribed"] = 1 if (user and PubSub.is_subscribed(user.username, owner_username)) else 0
        return card

    @classmethod
    async def generate_async(cls, workId: str, editionId: str, user: AuthenticatedUser | None) -> dict:
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
            cards: list[BookPageListCard] = []
            for lst in lists[: cls.LIMIT]:
                try:
                    cards.append(cls.get_list_card(lst, user))
                except Exception:  # noqa: BLE001  # one bad list shouldn't break the whole section
                    continue
            try:
                html = render_jinja_template(
                    "lists/carousel.html.jinja",
                    cards=cards,
                    has_more=len(lists) > cls.LIMIT,
                    all_url=all_url,
                )
            except Exception:  # noqa: BLE001  # same fallback the old saferender gave
                html = cls.RENDER_FALLBACK
            results["partials"].append(html)

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


class CarouselPartial:
    """Handler for lazily-loaded query carousels. Builds the eager carousel only here.

    Name is generic. Endpoint stays /partials/LazyCarousel.json for now.
    """

    @classmethod
    async def generate_async(cls, params: LazyCarouselParams, full_path: str = "/") -> dict:
        books = await gather_lazy_carousel_data_async(
            query=params.query,
            sort=params.sort,
            limit=params.limit,
            has_fulltext_only=params.has_fulltext_only,
            safe_mode=params.safe_mode,
        )
        # Build eager data here. Keep lazy logic in build_carousel_placeholder_config.
        # Apply safe_mode to the query for the book carousel as build_carousel_placeholder_config does for lazy.
        effective_query = f"{params.query} {_SAFE_MODE_FILTER}" if params.safe_mode else params.query
        book_data = get_carousel_data(
            books=[web.storage(b) for b in books["docs"]],
            title=params.title,
            url=params.url or "/search?" + urlencode({"q": effective_query, "sort": params.sort}),
            key=params.key,
            load_more={
                "queryType": "SEARCH",
                "q": effective_query,
                "limit": params.limit,
                "sorts": params.sort,
                "hasFulltextOnly": params.has_fulltext_only,
            },
            layout=params.layout,
            full_path=full_path,
        )
        data = EagerQueryCarouselData(
            search=params.search,
            query=effective_query,
            has_fulltext_only=params.has_fulltext_only,
            show=book_data["show"],
            title=book_data["title"],
            url=book_data["url"],
            key=book_data["key"],
            grid=book_data["grid"],
            compact=book_data["compact"],
            loadjs=book_data["loadjs"],
            config_json=book_data["config_json"],
            cards=book_data["cards"],
        )
        return {"partials": render_jinja_template("RawQueryCarousel.html.jinja", **data)}


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
    """Fetch carousel book data from Solr and return a typed dict with the docs."""
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


# Query carousels. Was macros/RawQueryCarousel.html + books/custom_carousel.html;
# the logic those two Templetor files carried lives here now.

CAROUSEL_EAGER_COVERS = 6  # cards past the first six lazy-load their cover image


def _carousel_card_book(book: Any) -> Any:
    """The record a card renders for ``book``: its first edition (Solr gives them
    as a list, or as a dict with ``docs``) else the book itself, with the authors
    and loan of the work. Things are kept as-is, dicts become web.storage so the
    card can use attribute access. Verbatim from books/custom_carousel.html.
    """
    editions = book.get("editions") or {}
    docs = editions.get("docs") if isinstance(editions, dict) else editions
    target = docs[0] if isinstance(docs, list) and docs else book
    card_book = target if hasattr(target, "key") else web.storage(target)
    card_book["authors"] = book.get("authors", [])
    if loan := book.get("loan"):
        card_book["loan"] = loan
    return card_book


class CarouselCommonData(TypedDict):
    """Shared display fields for all carousels. Keeps title, url, key in sync."""

    title: str | None
    url: str | None
    key: str


class CarouselQueryParams(CarouselCommonData):
    """Shared query fields for lazy and eager. Keeps query, sort, limit in sync."""

    query: str
    sort: str
    limit: int
    search: bool
    has_fulltext_only: bool
    layout: str
    fallback: str | bool | None
    safe_mode: bool


class BookCarouselData(CarouselCommonData):
    """Data for books/custom_carousel.html.jinja."""

    show: bool
    grid: str
    compact: str
    loadjs: str
    config_json: str
    cards: list[str]


class CarouselPlaceholderData(TypedDict):
    """Data for the lazy placeholder. Shows config JSON for lazy-carousel.js."""

    lazy_config_json: str
    loading_indicator_html: str
    fallback: str | bool | None


class EagerQueryCarouselData(BookCarouselData):
    """Data for the eager carousel. Holds search fields plus book carousel data."""

    search: bool
    query: str
    has_fulltext_only: bool


@public
def get_carousel_data(
    books: list | None = None,
    *,
    min_books: int = 1,
    load_more: dict | None = None,
    test: bool = False,
    compact_mode: bool = False,
    secondary_action: bool = False,
    layout: str = "carousel",
    full_path: str,
    **common: Unpack[CarouselCommonData],
) -> BookCarouselData:
    """Gather the data for books/custom_carousel.html.jinja.

    ``show`` is False when there are too few books and ``test`` is not set; the
    template then renders nothing, as the old Templetor ``$if`` did. @public so
    home/index.html, account/loans.html and account/mybooks.html can call it.
    """
    title = common.get("title", "")
    url = common.get("url", "")
    key = common.get("key", "")
    books = books or []
    if not (test or (books and len(books) >= min_books)):
        return BookCarouselData(show=False, title=title, url=url, key=key, grid="", compact="", loadjs="", config_json="", cards=[])

    config = {
        "booksPerBreakpoint": [4, 4, 4, 3, 2, 1] if compact_mode else [6, 5, 4, 3, 2, 1],
        "analyticsCategory": "BookCarousel",
        "carouselKey": key,
        "i18n": {"loading": _("Loading...")},
        "loadMore": (
            {
                "queryType": load_more.get("queryType", ""),
                "q": load_more.get("q", ""),
                "pageMode": load_more.get("mode", "offset"),
                "limit": load_more.get("limit", 18),
                "layout": layout,
                "key": key,
                "subject": load_more.get("subject", ""),
                "secondaryAction": secondary_action,
                "sorts": load_more.get("sorts", ""),
                "hasFulltextOnly": load_more.get("hasFulltextOnly", True),
            }
            if load_more
            else None
        ),
    }
    # The card is rendered here because get_carousel_card_data() returns flat keys and
    # Jinja cannot splat a dict into an {% include %}. Same pair as CarouselCardPartial.
    cards: list[str] = []
    for index, book in enumerate(books):
        try:
            card_book = _carousel_card_book(book)
            data = get_carousel_card_data(
                card_book,
                index >= CAROUSEL_EAGER_COVERS,
                layout,
                key,
                full_path,
                secondary_action=secondary_action,
            )
            cards.append(render_jinja_template("books/custom_carousel_card.html.jinja", **data))
        except Exception:  # noqa: BLE001  # one bad card does not stop the full carousel
            continue
    return BookCarouselData(
        show=True,
        title=title,
        url=url,
        key=key,
        grid="carousel--grid" if layout == "grid" else "",
        compact="carousel--compact" if compact_mode else "",
        loadjs="carousel--progressively-enhanced" if layout == "carousel" else "",
        config_json=json_encode(config),
        cards=cards,
    )


@public
def build_carousel_placeholder_config(**params: Unpack[CarouselQueryParams]) -> CarouselPlaceholderData:
    """Build config for the placeholder at macros/RawQueryCarouselPlaceholder.html.jinja.

    Builds the config JSON for lazy-carousel.js. No Solr call. Eager data is built
    only in CarouselPartial, which owns the Solr fetch.
    ``safe_mode`` adds the content_warning filter. For QueryCarousel.html.
    """
    query = params["query"]
    if params.get("safe_mode", True):
        query = f"{query} {_SAFE_MODE_FILTER}"
    config: dict[str, Any] = {
        "query": query,
        "sort": params.get("sort", "new"),
        "key": params.get("key", ""),
        "limit": params.get("limit", 20),
        "search": params.get("search", False),
        "has_fulltext_only": params.get("has_fulltext_only", True),
        "layout": params.get("layout", "carousel"),
        "fallback": params.get("fallback"),
        **({"title": params["title"]} if params.get("title") else {}),
        **({"url": params["url"]} if params.get("url") else {}),
    }
    return CarouselPlaceholderData(
        lazy_config_json=json_encode(config),
        # LoadingIndicator stays Templetor (10 other callers), so it is bridged
        # here and passed in, like the card's loan_status_html.
        loading_indicator_html=str(render_macro("LoadingIndicator", (_("Loading carousel"),), hidden=False)["__body__"]),
        fallback=params.get("fallback"),
    )


def setup():
    pass
