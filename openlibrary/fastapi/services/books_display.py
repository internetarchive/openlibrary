"""Service layer for `<ol-books-display>`: fetches a book query from Solr and
normalizes each doc into the flat card model the component renders.

The card model is deliberately label-free: the server returns a `cta` kind
(read / borrow / preview / ...) and the template supplies translated labels
via component attributes, matching how the other Lit components handle i18n.
"""

from __future__ import annotations

from hashlib import md5
from typing import Literal, TypedDict

from openlibrary.book_providers import EbookAccess, get_book_provider
from openlibrary.core import cache
from openlibrary.core.lending import get_lending_state
from openlibrary.plugins.upstream.utils import get_coverstore_public_url
from openlibrary.plugins.worksearch.code import work_search_async

# Same filter the legacy carousel applies (plugins/openlibrary/partials.py).
_SAFE_MODE_FILTER = '-subject:"content_warning:cover"'

# Superset of the legacy _CAROUSEL_FIELDS: adds author keys, ratings and the
# first-publish year for the list view, and ebook_access for partner CTAs.
BOOKS_DISPLAY_FIELDS = [
    "key",
    "title",
    "subtitle",
    "editions",
    "author_name",
    "author_key",
    "availability",
    "cover_i",
    "cover_edition_key",
    "ia",
    "ebook_access",
    "first_publish_year",
    "ratings_average",
    "ratings_count",
    "id_project_gutenberg",
    "id_project_runeberg",
    "id_librivox",
    "id_standard_ebooks",
    "id_openstax",
    "providers",
]

CtaKind = Literal[
    "read",
    "audiobook",
    "borrow",
    "special_access",
    "preview",
    "join_waitlist",
    "checked_out",
    "find_in_library",
    "not_in_library",
]


class BookAccess(TypedDict):
    state: str
    cta: CtaKind
    url: str | None
    external: bool
    method: Literal["get", "post"]
    login_intent: bool
    ocaid: str | None


class BookAuthor(TypedDict):
    key: str | None
    name: str


class BookCard(TypedDict):
    key: str
    title: str
    subtitle: str | None
    authors: list[BookAuthor]
    cover_url: str | None
    edition_key: str | None
    first_publish_year: int | None
    ratings_average: float | None
    ratings_count: int
    access: BookAccess


class BooksDisplayResponse(TypedDict):
    docs: list[BookCard]
    num_found: int
    offset: int
    limit: int


def _target_edition(work: dict) -> dict:
    """The doc the CTA is computed from: the `{!child}` edition when Solr
    returned one (availability is attached there), else the work itself."""
    editions = work.get("editions")
    if isinstance(editions, list) and editions:
        return editions[0]
    if isinstance(editions, dict) and editions.get("docs"):
        return editions["docs"][0]
    return work


def _cover_url(work: dict, edition: dict) -> str | None:
    host = get_coverstore_public_url()
    # Prefer the work's cover: which child edition Solr returns varies per query.
    cover_id = work.get("cover_i") or edition.get("cover_i")
    if cover_id and cover_id != -1:
        return f"{host}/b/id/{cover_id}-M.jpg"
    if ia := edition.get("ia") or work.get("ia"):
        return f"{host}/b/ia/{ia[0]}-M.jpg?default=false"
    if olid := edition.get("cover_edition_key") or work.get("cover_edition_key"):
        return f"{host}/b/olid/{olid}-M.jpg"
    return None


def _authors(work: dict) -> list[BookAuthor]:
    names = work.get("author_name") or []
    keys = work.get("author_key") or []
    return [{"key": f"/authors/{keys[i]}" if i < len(keys) else None, "name": name} for i, name in enumerate(names)]


def _partner_access(edition: dict, edition_key: str | None) -> BookAccess | None:
    provider = get_book_provider(edition)
    if not provider or provider.short_name == "ia" or not edition_key:
        return None
    acquisitions = sorted(
        (a for a in provider.get_acquisitions(edition) if a.ebook_access >= EbookAccess.PRINTDISABLED),
        key=lambda a: a.ebook_access,
        reverse=True,
    )
    if not acquisitions:
        return None
    acq = acquisitions[0]
    cta: CtaKind = ("audiobook" if acq.format == "audio" else "read") if acq.access == "open-access" else "preview"
    return BookAccess(
        state="partner",
        cta=cta,
        url=f"/books/{edition_key}/-/borrow?action=read",
        external=True,
        method="get",
        login_intent=False,
        ocaid=None,
    )


def build_access(edition: dict, user=None) -> BookAccess:
    """Collapse `get_lending_state()` + the LoanStatus macro's branches into a
    CTA the client can render without knowing lending rules."""
    availability = edition.get("availability") or {}
    ocaid = edition.get("ocaid") or availability.get("identifier")
    key = edition.get("key") or ""
    edition_key = key.split("/")[2] if key.startswith("/books/") else None
    state = get_lending_state(edition, user=user)
    stream_url = f"/borrow/ia/{ocaid}?ref=ol" if ocaid else None

    base: BookAccess = {
        "state": state,
        "cta": "not_in_library",
        "url": None,
        "external": False,
        "method": "get",
        "login_intent": False,
        "ocaid": ocaid,
    }

    if state == "partner":
        if partner := _partner_access(edition, edition_key):
            return partner
        state = "locate"
        base["state"] = state

    if state in ("borrowed", "open"):
        return {**base, "cta": "read", "url": stream_url}
    if state == "printdisabled":
        std_borrow = availability.get("available_to_borrow") or availability.get("available_to_browse")
        return {**base, "cta": "borrow" if std_borrow else "special_access", "url": stream_url, "login_intent": bool(std_borrow)}
    if state == "borrowable":
        return {**base, "cta": "borrow", "url": stream_url, "login_intent": True}
    if state == "waitlist":
        return {**base, "cta": "join_waitlist", "url": f"/borrow/ia/{ocaid}", "method": "post", "login_intent": True}
    if state == "checkedout":
        return {**base, "cta": "checked_out", "url": None}
    if state == "preview_only":
        return {**base, "cta": "preview", "url": f"https://archive.org/details/{ocaid}", "external": True}
    # locate
    if edition_key:
        return {**base, "cta": "find_in_library", "url": f"/books/{edition_key}/-/borrow?action=locate", "external": True}
    return base


def to_book_card(work: dict, user=None) -> BookCard:
    edition = _target_edition(work)
    key = edition.get("key") or ""
    return {
        "key": work.get("key") or "",
        "title": work.get("title") or edition.get("title") or "",
        "subtitle": work.get("subtitle") or None,
        "authors": _authors(work),
        "cover_url": _cover_url(work, edition),
        "edition_key": key.split("/")[2] if key.startswith("/books/") else None,
        "first_publish_year": work.get("first_publish_year"),
        "ratings_average": work.get("ratings_average"),
        "ratings_count": work.get("ratings_count") or 0,
        "access": build_access(edition, user=user),
    }


@cache.memoize(
    engine="memcache",
    key=lambda q, sort, limit, offset, has_fulltext_only, safe_mode: (
        "BooksDisplayData-" + md5(f"{q}-{sort}-{limit}-{offset}-{has_fulltext_only}-{safe_mode}".encode()).hexdigest()
    ),
    expires=300,
    cacheable=lambda key, value: "error" not in value,
)
async def _fetch_raw_docs(q: str, sort: str, limit: int, offset: int, has_fulltext_only: bool, safe_mode: bool) -> dict:
    """The Solr + availability round trip, cached like the legacy carousel.
    Per-user shaping happens outside the cache in `to_book_card`."""
    query = f"{q} {_SAFE_MODE_FILTER}".strip() if safe_mode and _SAFE_MODE_FILTER not in q else q
    params: dict = {"q": query}
    if has_fulltext_only:
        params["has_fulltext"] = "true"
    results = await work_search_async(
        params,
        sort=sort,
        fields=",".join(BOOKS_DISPLAY_FIELDS),
        limit=limit,
        offset=offset,
        facet=False,
        request_label="BOOK_CAROUSEL",
    )
    out = {"docs": results.get("docs", []), "num_found": results.get("num_found", 0)}
    if "error" in results:
        out["error"] = results["error"]
    return out


async def fetch_books_display(
    *,
    q: str,
    sort: str,
    limit: int,
    offset: int,
    has_fulltext_only: bool,
    safe_mode: bool,
    user=None,
) -> BooksDisplayResponse:
    raw = await _fetch_raw_docs(q, sort, limit, offset, has_fulltext_only, safe_mode)
    return {
        "docs": [to_book_card(work, user=user) for work in raw["docs"]],
        "num_found": raw["num_found"],
        "offset": offset,
        "limit": limit,
    }
