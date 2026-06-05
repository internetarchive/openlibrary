"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)

# Will include code from openlibrary.plugins.openlibrary.api
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Path, Query, status
from pydantic import BaseModel, BeforeValidator, Field
from starlette.responses import RedirectResponse

from openlibrary import accounts
from openlibrary.core import lending, models
from openlibrary.core.bestbook import Bestbook
from openlibrary.core.follows import PubSub
from openlibrary.core.models import Booknotes
from openlibrary.core.observations import get_observation_metrics
from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    get_authenticated_user,
    require_authenticated_user,
)
from openlibrary.fastapi.models import (
    Pagination,
    parse_comma_separated_list,
)
from openlibrary.plugins.openlibrary.api import bestbook_award, get_price_data_async
from openlibrary.plugins.openlibrary.api import ratings as legacy_ratings
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.views.loanstats import SINCE_DAYS, get_trending_books

SHOW_INTERNAL_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None
router = APIRouter(tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)

# Valid period values — mirrors SINCE_DAYS keys
# IMPORTANT: Keep this Literal in sync with the keys of views.loanstats.SINCE_DAYS!
# This guarantees that our path parameter validated by FastAPI is always
# a safe dictionary key when we pass it to the legacy backend function.
TrendingPeriod = Literal["now", "daily", "weekly", "monthly", "yearly", "forever"]


class AvailabilityStatusV2(BaseModel):
    """Model matching the shape of book availability data returned by IA/Lending."""

    status: str = Field(..., description="Availability status of the book")
    # error_message: str | None = None

    available_to_browse: bool | None = None
    available_to_borrow: bool | None = None
    available_to_waitlist: bool | None = None

    is_printdisabled: bool | None = None
    is_readable: bool | None = None
    is_lendable: bool | None = None
    is_previewable: bool = False
    is_restricted: bool = False
    is_browseable: bool | None = None

    identifier: str | None = None
    isbn: str | None = None
    oclc: str | None = None
    openlibrary_work: str | None = None
    openlibrary_edition: str | None = None

    last_loan_date: str | None = None
    num_waitlist: str | None = None
    last_waitlist_date: str | None = None

    model_config = {"extra": "allow"}


AvailabilityIDType = Literal["openlibrary_work", "openlibrary_edition", "identifier"]


class AvailabilityRequest(BaseModel):
    """Request body for bulk book availability queries (POST)."""

    ids: Annotated[list[str], Field(..., min_length=1, description="List of identifiers")]


@router.get(
    "/availability/v2",
    response_model=dict[str, AvailabilityStatusV2],
    description="Returns availability status for one or more books",
)
async def get_book_availability(
    id_type: Annotated[AvailabilityIDType, Query(alias="type", description="Type of the identifiers")],
    ids: Annotated[
        list[str],
        BeforeValidator(parse_comma_separated_list),
        Query(min_length=1, description="Comma-separated list of IDs (e.g. OL123W, ISBN, ocaid)"),
    ],
) -> dict:
    return await lending.get_availability_async(id_type, ids)


@router.post(
    "/availability/v2",
    response_model=dict[str, AvailabilityStatusV2],
    description="Returns availability status for one or more books",
)
async def post_book_availability(
    id_type: Annotated[AvailabilityIDType, Query(alias="type")],
    request: AvailabilityRequest,
) -> dict:
    return await lending.get_availability_async(id_type, request.ids)


class TrendingRequestParams(Pagination):
    limit: int = Field(100, ge=0, le=1000, description="Maximum number of results per page.")
    hours: int = Field(0, ge=0, description="Custom number of hours to look back.")
    days: int = Field(0, ge=0, description="Custom number of days to look back.")
    sort_by_count: bool = Field(True, description="Sort results by total log count (most-logged first).")
    minimum: int = Field(0, ge=0, description="Minimum log count a book must have to be included.")
    fields: Annotated[list[str] | None, BeforeValidator(parse_comma_separated_list)] = Field(
        None,
        description="Comma-separated list of Solr fields to include in each work.",
    )


class SolrWork(BaseModel):
    key: str
    title: str | None = None
    author_name: list[str] | None = None

    model_config = {"extra": "allow"}


class TrendingResponse(BaseModel):
    query: str = Field(..., description="Echo of the request path, e.g. /trending/daily")
    works: list[SolrWork] = Field(..., description="Trending work documents from Solr")
    days: int | None = Field(default=None, description="Look-back window in days (None = all-time)")
    hours: int = Field(..., description="Look-back window in hours")


@router.get(
    "/trending/{period}.json",
    response_model=TrendingResponse,
    response_model_exclude_none=True,
    description="Returns works sorted by recent activity (reads, loans, etc.)",
)
async def trending_books_api(
    period: Annotated[TrendingPeriod, Path(description="The time period for trending books")],
    params: Annotated[TrendingRequestParams, Query()],
) -> TrendingResponse:
    """Fetch trending books for the given period."""
    # ``period`` is always a key in SINCE_DAYS — guaranteed by the Literal type above.
    since_days: int | None = SINCE_DAYS.get(period, params.days)

    works = await get_trending_books(
        since_days=since_days,
        since_hours=params.hours,
        limit=params.limit,
        page=params.page,
        sort_by_count=params.sort_by_count,
        minimum=params.minimum,
        fields=params.fields,
    )

    return TrendingResponse(
        query=f"/trending/{period}",
        works=[SolrWork(**dict(work)) for work in works],
        days=since_days,
        hours=params.hours,
    )


@router.get("/browse.json")
async def browse(
    pagination: Annotated[Pagination, Depends()],
    q: Annotated[str, Query()] = "",
    subject: Annotated[str, Query()] = "",
    sorts: Annotated[list[str], BeforeValidator(parse_comma_separated_list), Query()] = [],  # noqa: B006
) -> dict:
    """
    Dynamically fetches the next page of books and checks if they are
    available to be borrowed from the Internet Archive without having
    to reload the whole web page.
    """

    url = lending.compose_ia_url(
        query=q,
        limit=pagination.limit,
        page=pagination.page,
        subject=subject,
        sorts=sorts,
    )

    works = await lending.get_available_async(url=url) if url else []
    return {"query": url, "works": [work.dict() for work in works]}


@router.get("/works/OL{work_id}W/ratings.json")
async def get_ratings(work_id: Annotated[int, Path()]) -> dict:
    """Get ratings summary for a work."""
    return legacy_ratings.get_ratings_summary(work_id)


@router.post("/works/OL{work_id}W/ratings.json")
async def post_ratings(
    work_id: Annotated[int, Path(gt=0)],
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    rating: Annotated[int | None, Form(ge=1, le=5)] = None,
    edition_id: Annotated[str | None, Form()] = None,
) -> dict[str, str]:
    """Register or remove a rating for a work.

    If rating is None, the existing rating is removed.
    If rating is provided, it must be in the valid range (1-5).
    """
    resolved_edition_id = int(extract_numeric_id_from_olid(edition_id)) if edition_id else None

    if rating is None:
        models.Ratings.remove(user.username, work_id)
        return {"success": "removed rating"}

    models.Ratings.add(
        username=user.username,
        work_id=work_id,
        rating=rating,
        edition_id=resolved_edition_id,
    )
    return {"success": "rating added"}


class BooknoteResponse(BaseModel):
    success: str = Field(..., description="Status message")


@router.post("/works/OL{work_id}W/notes", response_model=BooknoteResponse)
async def booknotes_post(
    work_id: Annotated[int, Path(gt=0)],
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    notes: Annotated[str | None, Form()] = None,
    edition_id: Annotated[str | None, Form(pattern=r"(?i)^OL\d+M$")] = None,
) -> BooknoteResponse:
    """
    Add or remove a note for a work (and optionally a specific edition).

    - If `notes` is provided: create or update the note.
    - If `notes` is omitted: remove the existing note.
    """
    resolved_edition_id = Booknotes.NULL_EDITION_VALUE
    if edition_id:
        resolved_edition_id = int(extract_numeric_id_from_olid(edition_id))

    if not notes:
        Booknotes.remove(user.username, work_id, edition_id=resolved_edition_id)
        return BooknoteResponse(success="removed note")

    Booknotes.add(
        username=user.username,
        work_id=work_id,
        notes=notes,
        edition_id=resolved_edition_id,
    )
    return BooknoteResponse(success="note added")


async def work_bookshelves():
    pass


async def work_editions():
    pass


async def author_works():
    pass


class PriceResponse(BaseModel):
    """Response model for the /prices.json endpoint."""

    amazon: dict[str, Any] = Field(default_factory=dict, description="Amazon pricing data")
    betterworldbooks: dict[str, Any] = Field(default_factory=dict, description="BetterWorldBooks pricing data")
    key: str | None = Field(None, description="Open Library edition key, if found")
    ocaid: str | None = Field(None, description="Internet Archive OCAID, if available")
    error: str | None = Field(None, description="Error message if request is invalid")

    model_config = {"extra": "allow"}


@router.get(
    "/prices.json",
    response_model=PriceResponse,
    response_model_exclude_none=True,
    description="Returns pricing data for a book from Amazon and BetterWorldBooks.",
)
async def price_api(
    isbn: Annotated[str | None, Query(description="ISBN-10 or ISBN-13", min_length=10, max_length=13)] = None,
    asin: Annotated[str | None, Query(description="Amazon ASIN", min_length=10, max_length=10)] = None,
) -> dict:
    """
    Returns pricing metadata from Amazon and BetterWorldBooks for a given book.
    Requires either an `isbn` or `asin` query parameter.
    """
    if not (isbn or asin):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="isbn or asin required",
        )

    return await get_price_data_async(isbn or "", asin or "")


class FollowEntry(BaseModel):
    subscriber: str
    publisher: str
    disabled: bool
    updated: datetime | None = None
    created: datetime | None = None


@router.get("/people/{username}/follows.json", response_model=list[FollowEntry])
async def get_patron_follows(
    username: Annotated[str, Path(pattern=r"^[^/]+$")],
    user: Annotated[AuthenticatedUser | None, Depends(get_authenticated_user)],
    redir_url: Annotated[str, Query()] = "",
) -> list[FollowEntry] | RedirectResponse:
    if not user or user.username != username:
        return RedirectResponse(url=f"/account/login?{urlencode({'redir_url': redir_url})}", status_code=303)
    return PubSub.get_following(username)


@router.post("/people/{username}/follows.json")
async def post_patron_follows(
    username: Annotated[str, Path(pattern=r"^[^/]+$")],
    user: Annotated[AuthenticatedUser | None, Depends(get_authenticated_user)],
    publisher: Annotated[str, Form()],
    redir_url: Annotated[str, Form()] = "/",
    state: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if not user or user.username != username:
        return RedirectResponse(url=f"/account/login?{urlencode({'redir_url': redir_url})}", status_code=303)
    if not accounts.find(username=publisher):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    action = PubSub.subscribe if state == "0" else PubSub.unsubscribe
    action(user.username, publisher)
    return RedirectResponse(url=redir_url, status_code=303)


async def patrons_observations():
    pass


@router.get(
    "/observations.json",
    description="Returns anonymized community reviews for a list of works.",
)
async def public_observations(
    olid: Annotated[list[str], Query(description="List of Work OLIDs")] = [],  # noqa: B006, mutable defaults are safe in fastapi
) -> dict:
    """
    Public observations fetches anonymized community reviews
    for a list of works. Useful for decorating search results.
    """
    return {"observations": {w: get_observation_metrics(w) for w in olid}}


class BestbookAwardResponse(BaseModel):
    success: bool | None = Field(None, description="Whether the award operation succeeded")
    award: int | None = Field(None, description="Award id returned by the award insert")
    rows: int | None = Field(None, description="Number of rows affected by award removal")
    errors: str | None = Field(None, description="Award operation error message")


class BestbookCountResponse(BaseModel):
    count: int = Field(..., description="Number of bestbook awards matching the filters")


BestbookAwardOp = Literal["add", "remove", "update"]


@router.post(
    "/works/OL{work_id}W/awards.json",
    response_model=BestbookAwardResponse,
    response_model_exclude_none=True,
)
async def post_bestbook_award(
    work_id: Annotated[int, Path(gt=0)],
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    query_op: Annotated[BestbookAwardOp | None, Query(alias="op")] = None,
    query_edition_key: Annotated[str | None, Query(alias="edition_key")] = None,
    query_topic: Annotated[str | None, Query(alias="topic")] = None,
    query_comment: Annotated[str | None, Query(alias="comment")] = None,
    form_op: Annotated[BestbookAwardOp | None, Form(alias="op")] = None,
    form_edition_key: Annotated[str | None, Form(alias="edition_key")] = None,
    form_topic: Annotated[str | None, Form(alias="topic")] = None,
    form_comment: Annotated[str | None, Form(alias="comment")] = None,
) -> dict:
    """Store, update, or remove a bestbook award for a work."""
    """
    This endpoint accepts both form data and query parameters, and uses an op parameter to indicate the requested operation.
    This is not the preferred API design; new endpoints should use standard HTTP methods instead.
    This structure is maintained only for backward compatibility with the legacy endpoint. Do not copy this pattern for new code.
    """
    return bestbook_award.process_bestbook_award(
        work_id=work_id,
        op=form_op if form_op is not None else query_op or "add",
        edition_key=form_edition_key if form_edition_key is not None else query_edition_key,
        topic=form_topic if form_topic is not None else query_topic,
        comment=form_comment if form_comment is not None else query_comment or "",
        username=user.username,
    )


@router.get("/awards/count.json", response_model=BestbookCountResponse)
async def get_bestbook_count(
    work_id: Annotated[str | None, Query()] = None,
    username: Annotated[str | None, Query()] = None,
    topic: Annotated[str | None, Query()] = None,
) -> BestbookCountResponse:
    """Get a count of bestbook awards matching the optional filters."""
    return BestbookCountResponse(count=Bestbook.get_count(work_id=work_id, username=username, topic=topic))


async def unlink_ia_ol():
    pass


async def monthly_logins():
    pass


# --- Activity Feed ---

_SHELF_LABELS: dict[int, str] = {
    1: "added to Want to Read",
    2: "is Currently Reading",
    3: "has Already Read",
    4: "stopped reading",
}


class ActivityItem(BaseModel):
    type: str
    shelf_id: int
    shelf_label: str
    username: str
    avatar_url: str
    work_key: str
    title: str
    cover_id: int | None = None
    author: str | None = None
    updated: str


class ActivityResponse(BaseModel):
    activity: list[ActivityItem]
    page: int


@router.get(
    "/api/internal/activity.json",
    response_model=ActivityResponse,
    response_model_exclude_none=True,
    description="Recent public reading log activity for the homepage activity feed.",
)
async def activity_feed_endpoint(
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
    page: Annotated[int, Query(ge=1)] = 1,
) -> ActivityResponse:
    import web

    from openlibrary.core.bookshelves import Bookshelves
    from openlibrary.core.models import User

    shelf_ids = [
        Bookshelves.PRESET_BOOKSHELVES["Want to Read"],
        Bookshelves.PRESET_BOOKSHELVES["Currently Reading"],
        Bookshelves.PRESET_BOOKSHELVES["Already Read"],
    ]

    # Fetch extra rows so we still hit `limit` after filtering private accounts
    batch = Bookshelves.get_recently_logged_books(
        shelf_ids=shelf_ids,
        limit=limit * 4,
        page=page,
    )
    if not batch:
        return ActivityResponse(activity=[], page=page)

    # Batch-check public_readlog from infogami store (one key per unique username)
    usernames = list({item["username"] for item in batch})
    public_set: set[str] = set()
    for username in usernames:
        prefs = web.ctx.site.store.get(f"/people/{username}/preferences") or {}
        if prefs.get("public_readlog", "no") == "yes":
            public_set.add(username)

    public_items = [item for item in batch if item["username"] in public_set][:limit]
    if not public_items:
        return ActivityResponse(activity=[], page=page)

    # Enrich with Solr work data (title, cover, author)
    await Bookshelves.add_solr_works_async(
        public_items,
        fields=["key", "title", "author_name", "cover_i"],
    )

    activity: list[ActivityItem] = []
    for item in public_items:
        work = item.get("work")
        if not work:
            continue
        authors = work.get("author_name") or []
        activity.append(
            ActivityItem(
                type="shelf_change",
                shelf_id=item["bookshelf_id"],
                shelf_label=_SHELF_LABELS.get(item["bookshelf_id"], "logged"),
                username=item["username"],
                avatar_url=User.get_avatar_url(item["username"]),
                work_key=f"/works/OL{item['work_id']}W",
                title=work.get("title", ""),
                cover_id=work.get("cover_i"),
                author=authors[0] if authors else None,
                updated=str(item.get("updated") or item.get("created") or ""),
            )
        )

    return ActivityResponse(activity=activity, page=page)
