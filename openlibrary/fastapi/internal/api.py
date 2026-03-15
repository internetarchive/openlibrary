"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)

# Will include code from openlibrary.plugins.openlibrary.api
"""

from __future__ import annotations

import os
from typing import Annotated, Literal

import web
from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, BeforeValidator, Field

from openlibrary.fastapi.models import Pagination, parse_fields_string
from openlibrary.utils.request_context import site as site_ctx
from openlibrary.views.loanstats import SINCE_DAYS, get_trending_books

router = APIRouter(tags=["internal"])

SHOW_INTERNAL_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None

# Valid period values — mirrors SINCE_DAYS keys
# IMPORTANT: Keep this Literal in sync with the keys of views.loanstats.SINCE_DAYS!
# This guarantees that our path parameter validated by FastAPI is always
# a safe dictionary key when we pass it to the legacy backend function.
TrendingPeriod = Literal["now", "daily", "weekly", "monthly", "yearly", "forever"]


class SolrWork(BaseModel):
    key: str
    title: str | None = None
    author_name: list[str] | None = None

    model_config = {"extra": "allow"}


class TrendingResponse(BaseModel):
    query: str = Field(..., description="Echo of the request path, e.g. /trending/daily")
    works: list[SolrWork] = Field(
        ...,
        description="Trending work documents from Solr",
        min_length=0,
    )
    days: int | None = Field(default=None, description="Look-back window in days (None = all-time)")
    hours: int = Field(..., description="Look-back window in hours")


@router.get("/availability/v2", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def book_availability():
    pass


class TrendingRequestParams(Pagination):
    limit: int = Field(100, ge=0, le=1000, description="Maximum number of results per page.")
    hours: int = Field(0, ge=0, description="Custom number of hours to look back.")
    sort_by_count: bool = Field(
        True,
        description="Sort results by total log count (most-logged first). Defaults to True, matching the legacy endpoint behaviour.",
    )
    minimum: int = Field(0, ge=0, description="Minimum log count a book must have to be included.")
    fields: Annotated[list[str] | None, BeforeValidator(parse_fields_string)] = Field(
        None,
        description="Comma-separated list of Solr fields to include in each work.",
    )


@router.get(
    "/trending/{period}.json",
    include_in_schema=SHOW_INTERNAL_IN_SCHEMA,
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
    since_days: int | None = SINCE_DAYS[period]
    web.ctx.site = site_ctx.get()

    try:
        works = get_trending_books(
            since_days=since_days,
            since_hours=params.hours,
            limit=params.limit,
            page=params.page,
            sort_by_count=params.sort_by_count,
            minimum=params.minimum,
            fields=params.fields,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch trending books from database.",
        ) from e

    return TrendingResponse(
        query=f"/trending/{period}",
        works=[SolrWork(**dict(work)) for work in works],
        days=since_days,
        hours=params.hours,
    )


async def browse():
    pass


async def ratings():
    pass


async def booknotes():
    pass


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


async def public_observations():
    pass


async def bestbook_award():
    pass


async def bestbook_count():
    pass


async def unlink_ia_ol():
    pass


async def monthly_logins():
    pass
