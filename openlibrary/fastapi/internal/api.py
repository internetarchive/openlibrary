"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)

# Will include code from openlibrary.plugins.openlibrary.api
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from openlibrary.core import models
from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    require_authenticated_user,
)
from openlibrary.plugins.openlibrary.api import ratings as legacy_ratings
from openlibrary.utils import extract_numeric_id_from_olid

router = APIRouter()

SHOW_INTERNAL_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None


@router.get("/availability/v2", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def book_availability():
    pass


@router.get("/trending/{period}.json", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def trending_books_api(period: str):
    pass


async def browse():
    pass


class RatingsRequest(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    edition_id: str | None = None


class RatingsSummary(BaseModel):
    """Summary statistics for a work's ratings."""

    average: float | None = Field(default=None, description="Average star rating")
    count: int = Field(default=0, description="Total number of ratings")
    sortable: float | None = Field(default=None, description="Bayesian sortable score")


class RatingsResponse(BaseModel):
    """Response model for the GET ratings endpoint."""

    summary: RatingsSummary = Field(default_factory=RatingsSummary)
    counts: dict[str, int] = Field(default_factory=dict, description="Per-star rating counts keyed by star number")


@router.get("/works/OL{work_id}W/ratings.json", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA, response_model=RatingsResponse)
async def get_ratings(work_id: Annotated[int, Path()]) -> dict:
    """Get ratings summary for a work."""
    return legacy_ratings.get_ratings_summary(work_id)


@router.post("/works/OL{work_id}W/ratings", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def post_ratings(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    work_id: Annotated[int, Path()],
    data: RatingsRequest,
) -> dict:
    """Register or remove a rating for a work.

    If rating is None, the existing rating is removed.
    If rating is provided, it must be in the valid range (0-5).
    """
    edition_id_int = int(extract_numeric_id_from_olid(data.edition_id)) if data.edition_id else None

    if data.rating is None:
        models.Ratings.remove(user.username, work_id)
        return {"success": "removed rating"}

    models.Ratings.add(
        username=user.username,
        work_id=work_id,
        rating=data.rating,
        edition_id=edition_id_int,
    )
    return {"success": "rating added"}


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
