"""
FastAPI endpoints for yearly reading goals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form
from pydantic import BaseModel, Field, model_validator

from openlibrary.core.yearly_reading_goals import YearlyReadingGoals
from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    require_authenticated_user,
)

router = APIRouter()

MAX_READING_GOAL = 10_000


class ReadingGoalItem(BaseModel):
    """A single reading goal entry."""

    year: int = Field(..., description="The year for this reading goal")
    goal: int = Field(..., description="The target number of books to read")


class ReadingGoalsResponse(BaseModel):
    """Response model for reading goals GET endpoint."""

    status: str = Field(default="ok", description="Response status")
    goal: list[ReadingGoalItem] = Field(default_factory=list, description="List of reading goals")


class ReadingGoalUpdateResponse(BaseModel):
    """Response model for reading goals POST endpoint."""

    status: str = Field(default="ok", description="Response status")


class ReadingGoalForm(BaseModel):
    """Form data for creating or updating a reading goal.

    Uses Pydantic model_validator to handle complex conditional validation
    that depends on multiple fields (is_update flag affects goal validation).
    """

    goal: int = Field(
        default=0,
        ge=0,
        le=MAX_READING_GOAL,
        description="Target number of books to read (0-10000). Use 0 with is_update to delete.",
    )
    year: int | None = Field(
        default=None,
        description="Year for this reading goal. Defaults to current year for creates, required for updates.",
    )
    is_update: str | None = Field(
        default=None,
        description="Set to any value to indicate this is an update operation (not create).",
    )

    @model_validator(mode="after")
    def validate_goal_logic(self) -> ReadingGoalForm:
        """Validate goal based on whether this is an update or create operation.

        - For creates: goal must be >= 1
        - For updates: goal must be >= 0, and year is required
        """
        is_update = self.is_update is not None

        if is_update:
            if not self.year:
                raise ValueError("Year required to update reading goals")
        elif not self.goal:
            raise ValueError("Reading goal must be a positive integer")

        return self


@router.get("/reading-goal.json", response_model=ReadingGoalsResponse)
async def get_reading_goals_endpoint(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    year: int | None = None,
) -> ReadingGoalsResponse:
    """Get reading goals for the authenticated user."""
    if year:
        records = YearlyReadingGoals.select_by_username_and_year(user.username, year)
    else:
        records = YearlyReadingGoals.select_by_username(user.username)
    goals = [
        ReadingGoalItem(
            year=getattr(record, "year", 0),
            goal=getattr(record, "target", 0),
        )
        for record in records
    ]

    return ReadingGoalsResponse(status="ok", goal=goals)


@router.post("/reading-goal.json", response_model=ReadingGoalUpdateResponse)
async def update_reading_goal_endpoint(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    form: Annotated[ReadingGoalForm, Form()],
) -> ReadingGoalUpdateResponse:
    """Create or update a reading goal for the authenticated user."""
    current_year = form.year or datetime.now().year
    if form.is_update is not None:
        # year is guaranteed to be not None here due to model_validator
        assert form.year is not None
        if form.goal == 0:
            YearlyReadingGoals.delete_by_username_and_year(user.username, form.year)
        else:
            YearlyReadingGoals.update_target(user.username, form.year, form.goal)
    else:
        YearlyReadingGoals.create(user.username, current_year, form.goal)

    return ReadingGoalUpdateResponse(status="ok")
