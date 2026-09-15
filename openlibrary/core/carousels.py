"""Canonical data fetching for the homepage "carousel" sections.

These carousels (staff picks, recently returned) used to fetch from the IA
advanced-search API while rendering inside `home/custom_ia_carousel.html`.
Fetching lives here so templates only ever render pre-fetched data, and so
both consumers — the homepage (`openlibrary.plugins.openlibrary.home`) and the
loans page (`openlibrary.plugins.upstream.account`) — build their carousels
from one shared module in `openlibrary.core` instead of importing from each
other's page controllers.
"""

from collections.abc import Iterable
from typing import Any, Literal, TypedDict

import web

from infogami.infobase.client import storify
from infogami.utils import delegate
from openlibrary.core import cache, ia, lending
from openlibrary.core.lending import compose_ia_url
from openlibrary.plugins.upstream.utils import convert_iso_to_marc, get_populated_languages
from openlibrary.utils.request_context import caching_prethread, get_request_lang

CAROUSELS_PRESETS = {
    "preset:comics": (
        '(subject:"comics" OR creator:("Gary Larson") OR creator:("Larson, Gary") '
        'OR creator:("Charles M Schulz") OR creator:("Schulz, Charles M") OR '
        'creator:("Jim Davis") OR creator:("Davis, Jim") OR creator:("Bill Watterson")'
        'OR creator:("Watterson, Bill") OR creator:("Lee, Stan"))'
    ),
    "preset:authorsalliance_mitpress": (
        "(openlibrary_subject:(authorsalliance) OR collection:(mitpress) OR publisher:(MIT Press) OR openlibrary_subject:(mitpress))"
    ),
}

CarouselName = Literal["staff_picks", "recently_returned"]

CAROUSEL_SUBJECTS: dict[CarouselName, str] = {
    "staff_picks": "openlibrary_staff_picks",
    "recently_returned": "",
}


class LoadMoreConfig(TypedDict):
    """Config passed to the carousel JS data-loader for lazy pagination."""

    queryType: str
    q: str
    subject: str
    sorts: str
    mode: str
    limit: int


class CarouselData(TypedDict):
    """Typed shape of a single carousel returned by get_carousel_data()."""

    books: list[Any]
    url: str | None
    load_more: LoadMoreConfig


def get_carousel_data(carousels: Iterable[CarouselName] | None = None) -> dict[CarouselName, CarouselData]:
    """Fetch books, IA search URLs, and load-more configs for the given carousels."""
    names: Iterable[CarouselName]
    if carousels is None:
        names = ("staff_picks", "recently_returned")
    else:
        names = carousels

    lang = get_request_lang()
    marc_lang = convert_iso_to_marc(lang)
    lang_filter = f" language:{marc_lang}" if marc_lang and marc_lang in get_populated_languages() else ""
    sorts = ["lending___last_browse desc"]
    limit = 18

    result: dict[CarouselName, CarouselData] = {}
    for name in names:
        subject = CAROUSEL_SUBJECTS[name]
        result[name] = {
            "books": generic_carousel(query=lang_filter, subject=subject, sorts=sorts, limit=limit, safe_mode=True),
            "url": compose_ia_url(
                query=lang_filter,
                subject=subject,
                sorts=sorts,
                limit=limit,
                advanced=False,
                safe_mode=True,
            ),
            "load_more": {
                "queryType": "BROWSE",
                "q": lang_filter,
                "subject": subject,
                "sorts": ",".join(sorts),
                "mode": "page",
                "limit": limit,
            },
        }
    return result


def get_ia_carousel_books(query=None, subject=None, sorts=None, limit=None, safe_mode=True):
    """Query the IA advanced-search API and return formatted book data for a carousel."""
    if "env" not in web.ctx:
        delegate.fakeload()

    elif query in CAROUSELS_PRESETS:
        query = CAROUSELS_PRESETS[query]

    limit = limit or lending.DEFAULT_IA_RESULTS
    books = lending.get_available(
        limit=limit,
        subject=subject,
        sorts=sorts,
        query=query,
        safe_mode=safe_mode,
    )
    formatted_books = [format_book_data(book, False) for book in books if book != "error"]
    return formatted_books


def generic_carousel(
    query=None,
    subject=None,
    sorts=None,
    limit=None,
    timeout=None,
    safe_mode=True,
):
    """Memoized carousel book fetch; falls back to a synchronous update on cache miss."""
    memcache_key = "home.ia_carousel_books"
    cached_ia_carousel_books = cache.memcache_memoize(
        get_ia_carousel_books,
        memcache_key,
        timeout=timeout or cache.DEFAULT_CACHE_LIFETIME,
        prethread=caching_prethread(),
    )
    books = cached_ia_carousel_books(
        query=query,
        subject=subject,
        sorts=sorts,
        limit=limit,
        safe_mode=safe_mode,
    )
    if not books:
        books = cached_ia_carousel_books.update(
            query=query,
            subject=subject,
            sorts=sorts,
            limit=limit,
            safe_mode=safe_mode,
        )[0]
    return storify(books) if books else books


def format_book_data(book, fetch_availability=True):
    """Format an IA search result / edition doc into the shape carousel cards consume."""
    d = web.storage()
    d.key = book.get("key")
    d.url = book.url()
    d.title = book.title or None
    d.ocaid = book.get("ocaid")
    d.eligibility = book.get("eligibility", {})
    d.availability = book.get("availability", {})

    def get_authors(doc):
        return [web.storage(key=a.key, name=a.name or None) for a in doc.get_authors()]

    work = book.works and book.works[0]
    d.authors = get_authors(work or book)
    d.work_key = work.key if work else book.key

    if cover := book.get_cover():
        d.cover_url = cover.url("M")
    elif d.ocaid:
        d.cover_url = "https://archive.org/services/img/%s" % d.ocaid

    if fetch_availability and d.ocaid:
        collections = ia.get_metadata(d.ocaid).get("collection", [])

        if "inlibrary" in collections:
            d.borrow_url = book.url("/borrow")
        else:
            d.read_url = book.url("/borrow")
    return d
