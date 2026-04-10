"""
FastAPI endpoints for patron check-ins.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, field_validator, model_validator

from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents
from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    require_authenticated_user,
)
from openlibrary.plugins.upstream.checkins import make_date_string
from openlibrary.utils import extract_numeric_id_from_olid

router = APIRouter()


class CheckInRequest(BaseModel):
    """Request model for creating/updating check-in events."""

    event_type: int
    year: int
    month: int | None = None
    day: int | None = None
    edition_key: str | None = None
    event_id: int | None = None

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: int) -> int:
        if not BookshelfEvent.has_value(v):
            raise ValueError("Invalid event type")
        return v

    @model_validator(mode="after")
    def validate_date(self) -> CheckInRequest:
        if self.day and not self.month:
            raise ValueError("Month is required when day is provided")
        return self


class CheckInResponse(BaseModel):
    """Response model for check-in operations."""

    status: str
    id: int


@router.post("/works/OL{work_id}W/check-ins")
async def create_or_update_patron_check_in(
    work_id: int,
    data: CheckInRequest,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> CheckInResponse:
    """Create or update a check-in event.

    If event_id is provided, updates existing event. Otherwise creates a new one.
    """
    edition_id = None
    if data.edition_key:
        edition_id = extract_numeric_id_from_olid(data.edition_key)

    date_str = make_date_string(data.year, data.month, data.day)

    if data.event_id:
        events = BookshelvesEvents.select_by_id(data.event_id)
        if not events:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )

        event = events[0]
        if user.username != event["username"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )

        BookshelvesEvents.update_event(data.event_id, event_date=date_str, edition_id=edition_id)
        event_id = data.event_id
    else:
        event_id = BookshelvesEvents.create_event(user.username, work_id, edition_id, date_str, event_type=data.event_type)

    return CheckInResponse(status="ok", id=event_id)


@router.delete("/check-ins/{check_in_id}")
async def delete_patron_check_in(
    check_in_id: int,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> Response:
    """Delete a check-in event by ID.

    The user can only delete their own check-in events.
    Returns 200 OK with empty body on success (matching web.py behavior).
    """
    events = BookshelvesEvents.select_by_id(check_in_id)
    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event does not exist",
        )

    event = events[0]
    if user.username != event["username"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    BookshelvesEvents.delete_by_id(check_in_id)
    return Response(status_code=status.HTTP_200_OK, content="")
