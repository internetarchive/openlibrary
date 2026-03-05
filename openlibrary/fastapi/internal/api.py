"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)

# Will include code from openlibrary.plugins.openlibrary.api
"""

from __future__ import annotations

import asyncio
import os
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from openlibrary.fastapi.models import Pagination  # noqa: TC001
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


def parse_comma_separated_list(fields_str: str) -> list[str] | None:
    return [f.strip() for f in fields_str.split(",") if f.strip()] or None


@router.get(
    "/trending/{period}.json",
    include_in_schema=SHOW_INTERNAL_IN_SCHEMA,
    response_model=TrendingResponse,
    response_model_exclude_none=True,
    description="Returns works sorted by recent activity (reads, loans, etc.)",
)
async def trending_books_api(
    period: Annotated[TrendingPeriod, Path(description="The time period for trending books")],
    pagination: Annotated[Pagination, Depends()],
    hours: Annotated[int, Query(ge=0, description="Custom number of hours to look back.")] = 0,
    sort_by_count: Annotated[
        bool,
        Query(description=("Sort results by total log count (most-logged first). Defaults to True, matching the legacy endpoint behaviour.")),
    ] = True,
    minimum: Annotated[
        int,
        Query(ge=0, description="Minimum log count a book must have to be included."),
    ] = 0,
    fields: Annotated[
        str,
        Query(description="Comma-separated list of Solr fields to include in each work."),
    ] = "",
) -> TrendingResponse:
    """Fetch trending books for the given period."""
    # ``period`` is always a key in SINCE_DAYS — guaranteed by the Literal type above.
    since_days: int | None = SINCE_DAYS[period]
    parsed_fields: list[str] | None = parse_comma_separated_list(fields)

    # get_trending_books is a synchronous DB call; run it in a thread pool to
    # avoid blocking the async event loop.
    try:
        works = await asyncio.to_thread(
            get_trending_books,
            since_days=since_days,
            since_hours=hours,
            limit=pagination.limit,
            page=pagination.page,
            sort_by_count=sort_by_count,
            minimum=minimum,
            fields=parsed_fields,
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
        hours=hours,
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
