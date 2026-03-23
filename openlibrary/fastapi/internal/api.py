"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)

# Will include code from openlibrary.plugins.openlibrary.api
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Path, Query
from pydantic import BaseModel, Field

from openlibrary.core import lending
from openlibrary.core.models import Booknotes
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.fastapi.models import Pagination  # noqa: TC001
from openlibrary.utils import extract_numeric_id_from_olid

router = APIRouter()

SHOW_INTERNAL_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None


@router.get("/availability/v2", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def book_availability():
    pass


@router.get("/trending/{period}.json", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def trending_books_api(period: str):
    pass


@router.get(
    "/browse.json",
    tags=["internal"],
    include_in_schema=SHOW_INTERNAL_IN_SCHEMA,
)
async def browse(
    pagination: Annotated[Pagination, Depends()],
    q: Annotated[str, Query()] = "",
    subject: Annotated[str, Query()] = "",
    sorts: Annotated[str, Query()] = "",
) -> dict:
    """
    Dynamically fetches the next page of books and checks if they are
    available to be borrowed from the Internet Archive without having
    to reload the whole web page.
    """
    sorts_list = [s.strip() for s in sorts.split(",") if s.strip()]

    url = lending.compose_ia_url(
        query=q,
        limit=pagination.limit,
        page=pagination.page,
        subject=subject,
        sorts=sorts_list,
    )

    works = lending.get_available(url=url) if url else []
    return {"query": url, "works": [work.dict() for work in works]}


async def ratings():
    pass


class BooknoteResponse(BaseModel):
    success: str = Field(..., description="Status message")


@router.post(
    "/works/OL{work_id}W/notes",
    response_model=BooknoteResponse,
    tags=["internal"],
    include_in_schema=SHOW_INTERNAL_IN_SCHEMA,
)
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
