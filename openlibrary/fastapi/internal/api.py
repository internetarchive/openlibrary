"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)

# Will include code from openlibrary.plugins.openlibrary.api
"""

from __future__ import annotations

import os
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, Path, Query
from pydantic import BaseModel, BeforeValidator, Field

from openlibrary.core import lending, models
from openlibrary.core.models import Booknotes
from openlibrary.core.observations import get_observation_metrics
from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    require_authenticated_user,
)
from openlibrary.fastapi.models import (
    Pagination,
    parse_comma_separated_list,
)
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
def get_book_availability(
    id_type: Annotated[AvailabilityIDType, Query(alias="type", description="Type of the identifiers")],
    ids: Annotated[
        list[str],
        BeforeValidator(parse_comma_separated_list),
        Query(min_length=1, description="Comma-separated list of IDs (e.g. OL123W, ISBN, ocaid)"),
    ],
) -> dict:
    return lending.get_availability(id_type, ids)


@router.post(
    "/availability/v2",
    response_model=dict[str, AvailabilityStatusV2],
    description="Returns availability status for one or more books",
)
def post_book_availability(
    id_type: Annotated[AvailabilityIDType, Query(alias="type")],
    request: AvailabilityRequest,
) -> dict:
    return lending.get_availability(id_type, request.ids)


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
def trending_books_api(
    period: Annotated[TrendingPeriod, Path(description="The time period for trending books")],
    params: Annotated[TrendingRequestParams, Query()],
) -> TrendingResponse:
    """Fetch trending books for the given period."""
    # ``period`` is always a key in SINCE_DAYS — guaranteed by the Literal type above.
    since_days: int | None = SINCE_DAYS.get(period, params.days)

    works = get_trending_books(
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

    works = lending.get_available(url=url) if url else []
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


async def price_api():
    pass


async def patrons_follows_json():
    pass


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


async def bestbook_award():
    pass


async def bestbook_count():
    pass


async def unlink_ia_ol():
    pass


async def monthly_logins():
    pass
