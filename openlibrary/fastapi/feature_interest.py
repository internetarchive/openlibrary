from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, status
from pydantic import BaseModel, Field

from openlibrary.core.patron_feature_interest import PatronFeatureInterestDB
from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    require_authenticated_user,
)

router = APIRouter()


class FeatureInterestForm(BaseModel):
    feature: str = Field(..., min_length=1, max_length=100)


class FeatureInterestResponse(BaseModel):
    status: str = "ok"
    already_recorded: bool = False


class FeatureInterestListResponse(BaseModel):
    status: str = "ok"
    features: list[str] = Field(default_factory=list)


@router.post("/account/feature-interest.json", response_model=FeatureInterestResponse)
async def record_feature_interest(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    form: Annotated[FeatureInterestForm, Form()],
) -> FeatureInterestResponse:
    """Record a patron's interest in a feature (idempotent)."""
    feature = form.feature.strip()
    if not feature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Feature required")

    exists = await PatronFeatureInterestDB.exists(user.username, feature)
    if not exists:
        await PatronFeatureInterestDB.create(user.username, feature)

    return FeatureInterestResponse(status="ok", already_recorded=exists)


@router.get("/account/feature-interest.json", response_model=FeatureInterestListResponse)
async def list_feature_interests(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    feature: Annotated[str | None, Query(description="Check specific feature")] = None,
) -> FeatureInterestListResponse:
    """Get all features the patron has expressed interest in, or check a specific one."""
    if feature:
        exists = await PatronFeatureInterestDB.exists(user.username, feature.strip())
        return FeatureInterestListResponse(status="ok", features=[feature] if exists else [])

    features = await PatronFeatureInterestDB.select_features_by_username(user.username)
    return FeatureInterestListResponse(status="ok", features=features)
