"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)

# Will include code from openlibrary.plugins.openlibrary.api
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from openlibrary.core import models
from openlibrary.core.ratings import Ratings
from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    require_authenticated_user,
)
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


# ---- Ratings Endpoints (migrated from openlibrary.plugins.openlibrary.api) ----


class RatingRequest(BaseModel):
    """Request model for POST /works/OL{id}W/ratings."""

    rating: int | None = None
    edition_id: str | None = None

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: int | None) -> int | None:
        if v is not None and v not in models.Ratings.VALID_STAR_RATINGS:
            raise ValueError("Invalid rating")
        return v



def _get_ratings_summary(work_id: int) -> dict:
    """Build ratings summary dict for a work, matching legacy response shape exactly."""
    if stats := Ratings.get_work_ratings_summary(work_id):
        return {
            "summary": {
                "average": stats["ratings_average"],
                "count": stats["ratings_count"],
                "sortable": stats["ratings_sortable"],
            },
            "counts": {
                "1": stats["ratings_count_1"],
                "2": stats["ratings_count_2"],
                "3": stats["ratings_count_3"],
                "4": stats["ratings_count_4"],
                "5": stats["ratings_count_5"],
            },
        }
    else:
        return {
            "summary": {
                "average": None,
                "count": 0,
            },
            "counts": {
                "1": 0,
                "2": 0,
                "3": 0,
                "4": 0,
                "5": 0,
            },
        }


@router.get("/works/OL{work_id}W/ratings", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def get_ratings(work_id: int) -> JSONResponse:
    """Get ratings summary for a work."""
    return JSONResponse(content=_get_ratings_summary(work_id))


@router.post("/works/OL{work_id}W/ratings", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def post_rating(
    work_id: int,
    data: RatingRequest,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> JSONResponse:
    """Register or remove a rating for a work.

    If rating is None, the existing rating is removed.
    If rating is provided, it must be in the valid range (0-5).
    """
    edition_id_int = int(extract_numeric_id_from_olid(data.edition_id)) if data.edition_id else None

    if data.rating is None:
        models.Ratings.remove(user.username, work_id)
        return JSONResponse(content={"success": "removed rating"})

    models.Ratings.add(
        username=user.username,
        work_id=work_id,
        rating=data.rating,
        edition_id=edition_id_int,
    )
    return JSONResponse(content={"success": "rating added"})


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
