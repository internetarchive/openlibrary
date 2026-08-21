"""
FastAPI endpoints for patron check-ins.
"""

from __future__ import annotations

from datetime import date as datetime_date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator

from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents
from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    require_authenticated_user,
)
from openlibrary.plugins.upstream.checkins import is_valid_date, make_date_string
from openlibrary.utils import extract_numeric_id_from_olid

router = APIRouter()


class CheckInRequest(BaseModel):
    """Request model for creating/updating check-in events."""

    event_type: int = Field(..., description="Event type enum value (1=start, 2=update, 3=finish)")
    year: int = Field(..., gt=0, le=9999, description="Four-digit year (1-9999)")
    month: int | None = Field(None, ge=1, le=12, description="Month (1-12)")
    day: int | None = Field(None, ge=1, le=31, description="Day (1-31)")
    edition_key: str | None = Field(
        None,
        pattern=r"(?i)^(?:/books/)?OL\d+M$",
        description="Edition OLID (e.g. OL123M)",
    )
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
        if not is_valid_date(self.year, self.month, self.day):
            raise ValueError("Invalid calendar date combination")
        if self.month and self.day:
            try:
                datetime_date(self.year, self.month, self.day)
            except ValueError:
                raise ValueError("Invalid calendar date combination")
        return self


class CheckInResponse(BaseModel):
    """Response model for check-in operations."""

    status: str
    id: int


@router.post("/works/OL{work_id}W/check-ins")
@router.post("/works/OL{work_id}W/check-ins.json")
async def create_or_update_patron_check_in(
    work_id: Annotated[int, Path(gt=0)],
    data: CheckInRequest,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> CheckInResponse:
    """Create or update a check-in event.

    If event_id is provided, updates existing event. Otherwise creates a new one.
    """
    edition_id = None
    if data.edition_key:
        raw_id = extract_numeric_id_from_olid(data.edition_key)
        if raw_id is not None:
            edition_id = int(raw_id)

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
    check_in_id: Annotated[int, Path(gt=0)],
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
