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
from pydantic import BaseModel

from openlibrary.core import lending
from openlibrary.fastapi.models import Pagination  # noqa: TC001

router = APIRouter()

SHOW_INTERNAL_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None


@router.get("/availability/v2", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def book_availability():
    pass


@router.get("/trending/{period}.json", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def trending_books_api(period: str):
    pass


class BrowseRequest(BaseModel):
    q: str = ""
    subject: str = ""
    sorts: str = ""


@router.get(
    "/browse.json",
    tags=["internal"],
    include_in_schema=SHOW_INTERNAL_IN_SCHEMA,
)
async def browse(request: Annotated[BrowseRequest, Depends()], pagination: Annotated[Pagination, Depends()]) -> dict:
    """
    Browse endpoint (migrated from openlibrary.plugins.openlibrary.api).
    Dynamically fetches the next page of books and checks if they are
    available to be borrowed from the Internet Archive without having
    to reload the whole web page.
    """
    sorts_list = [s.strip() for s in request.sorts.split(",") if s.strip()]

    url = lending.compose_ia_url(
        query=request.q,
        limit=pagination.limit,
        page=pagination.page,
        subject=request.subject,
        sorts=sorts_list,
    )

    works = lending.get_available(url=url) if url else []
    return {"query": url, "works": [work.dict() for work in works]}


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
