"""
FastAPI endpoints for yearly reading goals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query
from pydantic import BaseModel, Field

from openlibrary.core.yearly_reading_goals import YearlyReadingGoals
from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    require_authenticated_user,
)

router = APIRouter()

MAX_READING_GOAL = 10_000


class ReadingGoalItem(BaseModel):
    """A single reading goal entry."""

    year: int = Field(..., gt=0, le=9999, description="The year for this reading goal (1-9999)")
    goal: int = Field(..., description="The target number of books to read")


class ReadingGoalsResponse(BaseModel):
    """Response model for reading goals GET endpoint."""

    status: str = Field(default="ok", description="Response status")
    goal: list[ReadingGoalItem] = Field(default_factory=list, description="List of reading goals")


class ReadingGoalUpdateResponse(BaseModel):
    """Response model for reading goals POST endpoint."""

    status: str = Field(default="ok", description="Response status")


class ReadingGoalForm(BaseModel):
    """Form data for setting or deleting a reading goal.

    ``goal == 0`` deletes the goal for ``year``; any other value creates or
    updates it (upsert). ``year`` defaults to the current year.
    """

    goal: int = Field(
        ge=0,
        le=MAX_READING_GOAL,
        description="Target number of books to read (0-10000). Use 0 to delete the goal.",
    )
    year: int | None = Field(
        default=None,
        gt=0,
        le=9999,
        description="Year for this reading goal. Defaults to the current year.",
    )
    is_update: str | None = Field(
        default=None,
        description="Deprecated and ignored. Accepted so existing API callers don't break.",
    )


@router.get("/reading-goal.json", response_model=ReadingGoalsResponse)
async def get_reading_goals_endpoint(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    year: Annotated[int | None, Query(gt=0, le=9999, description="The year to filter goals by")] = None,
) -> ReadingGoalsResponse:
    """Get reading goals for the authenticated user."""
    if year:
        goal = await YearlyReadingGoals.select_by_username_and_year(user.username, year)
        records = [goal] if goal else []
    else:
        records = await YearlyReadingGoals.select_by_username(user.username)
    goals = [
        ReadingGoalItem(
            year=record.year,
            goal=record.target,
        )
        for record in records
    ]

    return ReadingGoalsResponse(status="ok", goal=goals)


@router.post("/reading-goal.json", response_model=ReadingGoalUpdateResponse)
async def update_reading_goal_endpoint(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    form: Annotated[ReadingGoalForm, Form()],
) -> ReadingGoalUpdateResponse:
    """Create or update a reading goal, or delete it when ``goal`` is 0."""
    year = form.year or datetime.now().year
    if form.goal == 0:
        await YearlyReadingGoals.delete_by_username_and_year(user.username, year)
    else:
        await YearlyReadingGoals.create(user.username, year, form.goal)

    return ReadingGoalUpdateResponse(status="ok")
