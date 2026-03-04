"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)

# Will include code from openlibrary.plugins.openlibrary.api
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from pydantic import BaseModel, Field

from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.utils import extract_numeric_id_from_olid

router = APIRouter()

SHOW_INTERNAL_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None


class BooknoteResponse(BaseModel):
    """Response model for booknote POST endpoint."""

    success: str = Field(..., description="Status message")


@router.get("/availability/v2", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def book_availability():
    pass


@router.get("/trending/{period}.json", tags=["internal"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)
async def trending_books_api(period: str):
    pass


async def browse():
    pass


async def ratings():
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


@router.post(
    "/works/OL{work_id}W/notes",
    response_model=BooknoteResponse,
    tags=["internal"],
    include_in_schema=SHOW_INTERNAL_IN_SCHEMA,
)
async def booknotes_post(
    work_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    notes: Annotated[str | None, Form()] = None,
    edition_id: Annotated[str | None, Form()] = None,
) -> BooknoteResponse:
    """
    Add or remove a note for a work (and optionally a specific edition).

    Mirrors the legacy `class booknotes(delegate.page)` in
    openlibrary/plugins/openlibrary/api.py

    - If `notes` is provided: create or update the note.
    - If `notes` is omitted: remove the existing note.
    """
    from openlibrary.core.models import Booknotes

    numeric_work_id = int(work_id)

    resolved_edition_id = (
        int(extract_numeric_id_from_olid(edition_id))
        if edition_id
        else Booknotes.NULL_EDITION_VALUE
    )

    try:
        if notes is None:
            Booknotes.remove(user.username, numeric_work_id, edition_id=resolved_edition_id)
            return BooknoteResponse(success="removed note")

        Booknotes.add(
            username=user.username,
            work_id=numeric_work_id,
            notes=notes,
            edition_id=resolved_edition_id,
        )
        return BooknoteResponse(success="note added")

    except Exception:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error communicating with the database",
        )
