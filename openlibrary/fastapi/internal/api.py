"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)

# Will include code from openlibrary.plugins.openlibrary.api
"""

from __future__ import annotations

import asyncio
import os
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

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


class WorkModel(BaseModel):
    model_config = {"extra": "allow"}
    key: str
    title: str | None = None


class BrowseRequest(BaseModel):
    q: str = ""
    subject: str = ""
    sorts: str = ""


class BrowseResponse(BaseModel):
    query: str = Field(..., description="The IA search URL generated")
    works: list[WorkModel] = []


@router.get(
    "/browse.json",
    tags=["internal"],
    include_in_schema=SHOW_INTERNAL_IN_SCHEMA,
    response_model=BrowseResponse,
    response_model_exclude_none=False,
)
async def browse(request: Annotated[BrowseRequest, Depends()], pagination: Annotated[Pagination, Depends()]) -> BrowseResponse:
    """Browse endpoint (migrated from openlibrary.plugins.openlibrary.api)."""
    sorts_list = [s.strip() for s in request.sorts.split(",") if s.strip()]

    url = lending.compose_ia_url(
        query=request.q,
        limit=pagination.limit,
        page=pagination.page,
        subject=request.subject,
        sorts=sorts_list,
    )

    if not url:
        works = []
    else:
        works = await asyncio.to_thread(lending.get_available, url=url)

    processed_works = []
    if isinstance(works, list):
        for work in works:
            if isinstance(work, str) and (work.lower() == "error" or not work):
                continue

            if isinstance(work, str):
                processed_works.append(WorkModel(key=work))
            elif hasattr(work, "dict"):
                processed_works.append(WorkModel(**work.dict()))
            elif isinstance(work, dict):
                if work.get("key") == "error":
                    continue
                processed_works.append(WorkModel(**work))
            elif hasattr(work, "key"):
                processed_works.append(WorkModel(key=work.key))

    return BrowseResponse(query=url or "", works=processed_works)


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
