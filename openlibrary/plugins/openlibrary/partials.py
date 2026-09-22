from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from hashlib import md5
from typing import TYPE_CHECKING, Any, Literal, NotRequired, TypedDict, Unpack
from urllib.parse import parse_qs, quote, quote_plus

import web
from markupsafe import Markup
from pydantic import BaseModel, Field

from infogami.utils.view import public
from openlibrary.book_providers import get_book_provider, get_cover_url
from openlibrary.core import cache
from openlibrary.core.follows import PubSub
from openlibrary.core.fulltext import fulltext_search_async
from openlibrary.core.helpers import affiliate_id, commify, datestr, datetimestr_utc
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

logger = logging.getLogger("openlibrary.plugins.openlibrary.partials")


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
# NOTE: Hard-coded to keep behavior unchanged during the Templetor to Jinja
# conversion (PR 13578, issue 13570): the since-deleted Templetor template
# `books/custom_carousel_card.html` hard-coded this host, and the DOM must stay
# identical. Consider using `get_coverstore_public_url()` in a follow-up change.
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


# Temporarily disabled; the Amazon price request times out.
AMAZON_PRICE_FETCH_ENABLED = False


@dataclass(frozen=True, slots=True)
class AffiliateStoreBuildContext:
    title: str
    isbn: str | None
    asin: str | None
    bwb_metadata: BetterWorldBooksMetadata | None
    amz_metadata: dict | None
    author: str | None = None

    @property
    def search_terms(self) -> str:
        """What to search a store's catalogue for when there is no isbn to link to."""
        return " ".join(filter(None, (self.title, self.author)))


@dataclass(frozen=True, slots=True)
class AffiliateOffer:
    """One way to buy the book at a store, e.g. used copies from $4.28."""

    price: str
    amount: float
    condition: str | None = None  # "new", "used", "collectible" or "refurbished"; None when unstated
    sub_condition: str | None = None  # "like_new", "very_good", "good" or "acceptable"
    quantity: int | None = None
    list_price: str | None = None  # the pre-discount price, struck through
    savings_pct: int | None = None


@dataclass(frozen=True, slots=True)
class AffiliateStore:
    key: str
    analytics_key: str
    name: str
    link: str
    offers: tuple[AffiliateOffer, ...] = ()
    # The store's own words, shown as given: stock/shipping text, seller, deal label
    availability: str | None = None
    seller: str | None = None
    deal: str | None = None
    out_of_stock: bool = False

    @property
    def lowest_offer(self) -> AffiliateOffer | None:
        return min(self.offers, key=lambda offer: offer.amount, default=None)


def _bwb_offers(bwb: BetterWorldBooksMetadata) -> tuple[AffiliateOffer, ...]:
    offers = []
    for condition, price, quantity in (("new", bwb.get("new_price"), bwb.get("new_qty")), ("used", bwb.get("used_price"), bwb.get("used_qty"))):
        if price and quantity != 0:
            offers.append(AffiliateOffer(price=f"${price}", amount=float(price), condition=condition, quantity=quantity))
    if not offers and (price := bwb.get("price_amt")):
        # Cached metadata from before per-condition prices were recorded
        offers.append(AffiliateOffer(price=f"${price}", amount=float(price), condition=bwb.get("qlt")))
    return tuple(offers)


def _amazon_offer(amz: dict) -> AffiliateOffer | None:
    if not (price := amz.get("price")) or not (cents := amz.get("price_amt")):
        return None
    savings_pct = amz.get("price_savings_pct")
    return AffiliateOffer(
        price=price,
        amount=cents / 100,
        condition=(amz.get("condition") or "").lower() or None,
        sub_condition=_snake_case(amz.get("sub_condition")),
        list_price=amz.get("list_price"),
        savings_pct=round(savings_pct) if savings_pct else None,
    )


def _snake_case(value: str | None) -> str | None:
    """Amazon's "LikeNew" -> "like_new"."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower() if value else None


def _bookshop_link(ctx: AffiliateStoreBuildContext) -> str | None:
    affiliate = affiliate_id("bookshop-org")
    if ctx.isbn:
        return f"https://bookshop.org/a/{affiliate}/{ctx.isbn}"
    if not ctx.search_terms:
        return None
    # Unverified: whether Bookshop credits the affiliate on a search page, and under this param
    return f"https://bookshop.org/beta-search?keywords={quote_plus(ctx.search_terms)}&affiliate={affiliate}"


def build_stores(ctx: AffiliateStoreBuildContext) -> list[AffiliateStore]:
    """Build affiliate store data, in display order, for rendering in
    AffiliateLinks.html.jinja. A book with no isbn links to each store's
    search results instead of to a product page."""

    bwb_link = f"https://www.betterworldbooks.com/search/results?q={quote_plus(ctx.search_terms)}"
    if ctx.isbn:
        bwb_link = f"https://www.betterworldbooks.com/product/detail/{ctx.isbn}"

    bwb, amz = ctx.bwb_metadata, ctx.amz_metadata
    stores: list[AffiliateStore] = [
        AffiliateStore(
            key="betterworldbooks",
            analytics_key="BetterWorldBooks",
            name=_("Better World Books"),
            link=bwb_link,
            offers=_bwb_offers(bwb) if bwb else (),
            # Only an explicit zero on both counts; a missing listing says nothing about stock
            out_of_stock=bwb is not None and bwb.get("new_qty") == 0 and bwb.get("used_qty") == 0,
        )
    ]

    if amazon_link := amazon_affiliate_url(ctx.isbn, ctx.asin, affiliate_id("amazon"), query=ctx.search_terms):
        # BWB's lookup includes Amazon's lowest market price, so prefer it over a second request
        offer: AffiliateOffer | None
        if market_price := bwb.get("market_price") if bwb else None:
            offer = AffiliateOffer(price=market_price, amount=float(market_price.lstrip("$")))
        else:
            offer = _amazon_offer(amz) if amz else None
        stores.append(
            AffiliateStore(
                key="amazon",
                analytics_key="Amazon",
                name=_("Amazon"),
                link=amazon_link,
                offers=(offer,) if offer else (),
                availability=amz.get("availability_message") if amz else None,
                seller=amz.get("merchant") if amz else None,
                deal=amz.get("deal_badge") if amz else None,
            )
        )

    if bookshop_link := _bookshop_link(ctx):
        stores.append(
            AffiliateStore(
                key="bookshop-org",
                analytics_key="BookshopOrg",
                name=_("Bookshop.org"),
                link=bookshop_link,
            )
        )

    return stores


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
        should_fetch_prices = prices and not is_bot()
        if should_fetch_prices and isbn:
            bwb_metadata = await get_betterworldbooks_metadata(isbn)
            if AMAZON_PRICE_FETCH_ENABLED and (not bwb_metadata or not bwb_metadata.get("market_price")):
                amz_metadata = await get_amazon_metadata_async(isbn, resources="prices")

        if bwb_metadata and "error" in bwb_metadata:
            bwb_metadata = None

        ctx = AffiliateStoreBuildContext(title, isbn, asin, bwb_metadata, amz_metadata)
        return {"partials": _render_affiliate_links(ctx)}


def _render_affiliate_links(ctx: AffiliateStoreBuildContext, price_lookup: dict | None = None) -> str:
    template = get_jinja_env().get_template("AffiliateLinks.html.jinja")
    return template.render(stores=build_stores(ctx), price_lookup=price_lookup)


@public
def render_affiliate_links(title: str, isbn: str | None, asin: str | None, prices: bool, author: str | None = None) -> str:
    """Render the Buy popover's store rows with the page. When prices apply,
    the section carries a price lookup that affiliate-links.js fills in later."""
    ctx = AffiliateStoreBuildContext(title, isbn, asin, None, None, author)
    price_lookup = {"title": title, "isbn": isbn, "asin": asin or ""} if prices and isbn else None
    return _render_affiliate_links(ctx, price_lookup)


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


def get_fulltext_suggestion_item_data(doc: Any) -> dict[str, Any]:
    """Prepare display data for a full-text search suggestion item."""
    doc_type = (
        "infogami_work"
        if doc.get("type", {}).get("key") == "/type/work"
        else "infogami_edition"
        if doc.get("type", {}).get("key") == "/type/edition"
        else "solr_work"
        if not doc.get("editions")
        else "solr_edition"
    )
    selected_ed = doc.get("editions")[0] if doc_type == "solr_edition" else doc
    book_url = doc.url() if doc_type.startswith("infogami_") else doc.key

    if doc_type == "solr_edition":
        work_edition_url = book_url + "?edition=" + quote("key:" + selected_ed.key)
    elif (book_provider := get_book_provider(doc)) and doc_type.endswith("_work"):
        work_edition_url = book_url + "?edition=" + quote(book_provider.get_best_identifier_slug(doc))
    else:
        work_edition_url = book_url

    edition_work = doc["works"][0] if doc_type == "infogami_edition" and "works" in doc else None
    full_title = selected_ed.get("title", "") + (": " + selected_ed.subtitle if selected_ed.get("subtitle") else "")

    authors = None
    if doc_type == "infogami_work":
        authors = doc.get_authors()
    elif doc_type == "infogami_edition":
        authors = edition_work.get_authors() if edition_work else doc.get_authors()
    elif "authors" in doc:
        authors = doc["authors"]
    elif "author_key" in doc:
        authors = [{"key": "/authors/" + key, "name": name} for key, name in zip(doc["author_key"], doc["author_name"])]

    author_data = (
        [
            {
                "name": author.get("name") or author.get("author", {}).get("name"),
                "url": author.get("url") or author.get("key") or author.get("author", {}).get("url") or author.get("author", {}).get("key"),
            }
            for author in authors
        ]
        if authors
        else None
    )
    byline_html = (
        Markup(
            str(
                render_macro(
                    "BookByline",
                    (author_data,),
                    limit=9,
                    overflow_url=work_edition_url,
                    attrs='class="results"',
                )["__body__"]
            )
        )
        if author_data
        else None
    )
    return {
        "author_data": author_data,
        # BookByline remains Templetor, so render the bridge while the web.py
        # macro registry is available and hand trusted HTML to Jinja.
        "byline_html": byline_html,
        "blur_cover": "",
        "cover": get_cover_url(selected_ed) or "/static/images/icons/avatar_book-sm.png",
        "full_title": full_title,
        "work_edition_url": work_edition_url,
    }


def get_fulltext_suggestion_snippet_data(doc: dict[str, Any]) -> dict[str, str | Markup]:
    """Prepare snippet display data returned by the full-text search service."""
    page_nums = doc.get("fields", {}).get("page_num", [])
    if len(page_nums) == 1 and isinstance(page_nums[0], list):
        page_nums = page_nums[0]
    snippet = doc.get("highlight", {}).get("text", [""])[0]
    snippet_html = Markup(
        snippet.replace("<", "&laquo;").replace(">", "&raquo;").replace("{{{", "<mark class='highlight'><strong>").replace("}}}", "</strong></mark>")
    )
    return {
        "ia": doc.get("fields", {}).get("identifier", [""])[0],
        "page": ", ".join(str(num) for num in page_nums),
        "snippet_html": snippet_html,
    }


class FullTextSuggestionsPartial:
    """Handler for rendering full-text search suggestions."""

    @classmethod
    async def generate_async(cls, query: str) -> FullTextSuggestionsPartialResult:
        data = await fulltext_search_async(query)
        hits = data.get("hits", {})
        if not hits.get("total"):
            macro = "<div></div>"
        else:
            suggestions = [
                {
                    "item": get_fulltext_suggestion_item_data(hit["edition"]),
                    "snippet": get_fulltext_suggestion_snippet_data(hit),
                }
                for hit in hits.get("hits", [])[:4]
                if hit.get("edition")
            ]
            macro = render_jinja_template(
                "FulltextSearchSuggestion.html.jinja",
                # LoadingIndicator remains Templetor (10 other callers), so
                # render the bridge before entering the Jinja environment.
                loading_indicator_html=Markup(str(render_macro("LoadingIndicator", (_("Checking for Search Inside matches"),))["__body__"])),
                num_found=commify(hits.get("total", 0)),
                query_url="/search/inside?" + urlencode({"q": query}),
                suggestions=suggestions,
            )
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
        book_data = get_book_carousel_data(
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
def get_book_carousel_data(
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


# A ddc_sort value like "813.54" or "813" (no decimal). Non-numeric ddc_sort
# values (e.g. "[Fic]", "[E]") are rejected, since they sort lexically after
# every number and would otherwise show up as false shelf-neighbours.
_NUMERIC_DDC_RE = re.compile(r"^\d{1,3}(\.\d+)?$")

# Solr's ddc_sort field never goes above this; used to cap the upper end of
# the "after" range so it can't run into non-numeric ddc_sort values.
_MAX_NUMERIC_DDC = "999.99999"

# Number of results to pull from the "exact same ddc_sort" bucket, vs. from
# each of the strict before/after ranges. A common ddc_sort value (e.g.
# "813.54") can have tens of thousands of works, all tied on sort order, so
# these are kept small and deliberate rather than let one bucket crowd out
# real neighbours below/above it.
_EXACT_MATCH_ROWS = 4
_RANGE_ROWS = 8
_MAX_NEARBY_BOOKS = _EXACT_MATCH_ROWS + 2 * _RANGE_ROWS

# Same readability cut the sibling carousels on the book page use: borrowable
# or public ebooks only. The range queries are open-ended and distance-sorted,
# so Solr just walks further along the shelf to fill the rows.
_READABLE_FILTER = "ebook_access:[borrowable TO *]"


class NearbyBooksParams(BaseModel):
    """Parameters for the book page's "Nearby Books" (DDC shelf-adjacency) carousel."""

    work_key: str = Field(pattern=r"^/works/OL\d+W$")
    language: str | None = Field(None, pattern=r"^[a-z]{3}$")
    limit: int = Field(_MAX_NEARBY_BOOKS, ge=1, le=_MAX_NEARBY_BOOKS)


@public
def build_nearby_books_placeholder_config(work_key: str, language: str | None = None) -> CarouselPlaceholderData:
    """Build config for the Nearby Books placeholder (macros/RawQueryCarouselPlaceholder.html.jinja).

    The ``partial`` key tells lazy-carousel.js to fetch from /partials/NearbyBooks.json
    instead of the default LazyCarousel endpoint.
    """
    config = {"partial": "NearbyBooks", "work_key": work_key, **({"language": language} if language else {})}
    return CarouselPlaceholderData(
        lazy_config_json=json_encode(config),
        loading_indicator_html=str(render_macro("LoadingIndicator", (_("Loading carousel"),), hidden=False)["__body__"]),
        fallback=None,
    )


@cache.memoize(
    engine="memcache",
    key=lambda work_key, language, limit: "NearbyBooks-" + md5(f"{work_key}-{language}-{limit}".encode()).hexdigest(),
    expires=300,
    # None means Solr failed; don't pin that for five minutes.
    cacheable=lambda key, value: value is not None,
)
async def gather_nearby_books_async(
    work_key: str,
    language: str | None,
    limit: int,
) -> list[dict] | None:
    """Fetch works with numerically adjacent ddc_sort values from Solr.

    Anchors on the *work's* indexed ddc_sort (the longest ddc string across
    all of the work's editions, per work.py) rather than recomputing a ddc
    from whichever single edition is being viewed -- otherwise the "shelf
    position" being browsed wouldn't match the axis the shelf is actually
    sorted on.

    Finds a few exact matches at that ddc_sort, plus strict (exclusive)
    neighbours below and above it, using Solr's `{`/`}` exclusive range
    bounds so a popular ddc_sort value can't fill both ranges with ties on
    itself. Both ranges are capped to numeric ddc_sort values only, since
    non-numeric values (e.g. "[Fic]", "[E]") sort lexically after every
    number and would otherwise show up as false neighbours. Only readable
    (borrowable or public) works count as neighbours, matching the other
    book-page carousels.

    Returns None (not cached) when Solr fails.
    """
    from openlibrary.plugins.worksearch.search import get_solr

    solr = get_solr()
    safe_work_key = solr.escape(work_key)

    # ddc_sort is stored=false, so read it through /select (docValues are
    # returned there) rather than /get, which may serve from the update log.
    try:
        anchor_res = await solr.select_async(f'key:"{safe_work_key}"', fields=["ddc_sort"], rows=1)
    except Exception:
        logger.exception("gather_nearby_books_async failed to fetch ddc_sort for %r", work_key)
        return None

    anchor_docs = anchor_res.docs if anchor_res and anchor_res.docs else []
    ddc = anchor_docs[0].get("ddc_sort") if anchor_docs else None
    if not ddc or not _NUMERIC_DDC_RE.match(ddc):
        return []

    lang_clause = f' AND language:"{solr.escape(language)}"' if language else ""
    work_filter = f' -key:"{safe_work_key}"'
    # Joined with AND on purpose: a bare clause after an AND chain is only a
    # SHOULD for Solr's classic parser, which would boost rather than filter.
    common = f" AND {_READABLE_FILTER}{lang_clause}{work_filter} {_SAFE_MODE_FILTER}"

    try:
        exact_res, before_res, after_res = await asyncio.gather(
            solr.select_async(
                f'type:work AND ddc_sort:"{ddc}"{common}',
                fields=_CAROUSEL_FIELDS,
                rows=_EXACT_MATCH_ROWS,
            ),
            solr.select_async(
                f'type:work AND ddc_sort:["000" TO "{ddc}"}}{common}',
                fields=_CAROUSEL_FIELDS,
                rows=_RANGE_ROWS,
                sort="ddc_sort desc",
            ),
            solr.select_async(
                f'type:work AND ddc_sort:{{"{ddc}" TO "{_MAX_NUMERIC_DDC}"]{common}',
                fields=_CAROUSEL_FIELDS,
                rows=_RANGE_ROWS,
                sort="ddc_sort asc",
            ),
        )
    except Exception:
        logger.exception("gather_nearby_books_async failed for %r (ddc_sort=%r)", work_key, ddc)
        return None

    before_docs = list(reversed(before_res.docs)) if before_res and before_res.docs else []
    exact_docs = exact_res.docs if exact_res and exact_res.docs else []
    after_docs = after_res.docs if after_res and after_res.docs else []

    seen: set[str] = set()
    unique_docs: list[dict] = []
    for doc in before_docs + exact_docs + after_docs:
        key = doc.get("key")
        if key and key not in seen:
            seen.add(key)
            unique_docs.append(doc)

    return unique_docs[:limit]


class NearbyBooksPartial:
    """Handler for the book page's "Nearby Books" (DDC shelf-adjacency) carousel."""

    @classmethod
    async def generate_async(cls, params: NearbyBooksParams, full_path: str = "/") -> dict:
        books = await gather_nearby_books_async(
            work_key=params.work_key,
            language=params.language,
            limit=params.limit,
        )
        if not books:
            return {"partials": ""}

        # No query backs this carousel, so no title link and no load-more.
        data = get_book_carousel_data(
            books=[web.storage(b) for b in books],
            title=_("Nearby Books"),
            url=None,
            key="nearby-books",
            full_path=full_path,
        )
        return {"partials": render_jinja_template("books/custom_carousel.html.jinja", **data)}


def setup():
    pass
