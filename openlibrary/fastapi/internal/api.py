"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)

# Will include code from openlibrary.plugins.openlibrary.api
"""

from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from openlibrary.core import lending

router = APIRouter()

SHOW_INTERNAL_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None


@router.get("/availability/v2", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def book_availability():
    pass


@router.get("/trending/{period}.json", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def trending_books_api(period: str):
    pass


@router.get("/browse.json", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def browse(q: str = "", page: int = 1, limit: int = 100, subject: str = "", sorts: str = "") -> JSONResponse:
    """Browse endpoint (migrated from openlibrary.plugins.openlibrary.api)."""
    sorts_list = sorts.split(",")

    url = lending.compose_ia_url(
        query=q,
        limit=limit,
        page=page,
        subject=subject,
        sorts=sorts_list,
    )

    works = lending.get_available(url=url) if url else []

    result = {
        "query": url,
        "works": [work.dict() for work in works],
    }

    return JSONResponse(content=result)


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
