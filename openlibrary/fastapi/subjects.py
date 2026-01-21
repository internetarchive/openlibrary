from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, model_validator

from openlibrary.core.models import Subject
from openlibrary.fastapi.models import Pagination
from openlibrary.plugins.worksearch.subjects import (
    DEFAULT_RESULTS,
    MAX_RESULTS,
    date_range_to_publish_year_filter,
    get_subject,
)

router = APIRouter()


class SubjectRequestParams(Pagination):
    """Query parameters for /subjects/{key}.json endpoint."""

    details: Literal["true", "false"] = Field(
        "false", description="Include facets and detailed metadata"
    )
    has_fulltext: Literal["true", "false"] = Field(
        "false", description="Filter to works with fulltext"
    )
    sort: str = Field(
        "editions", description="Sort order: editions, old, new, ranking, etc."
    )
    available: Literal["true", "false"] = Field(
        "false", description="Filter to available works"
    )
    published_in: str | None = Field(
        None, description="Date range filter: YYYY or YYYY-YYYY"
    )

    @model_validator(mode="after")
    def set_default_limit(self) -> SubjectRequestParams:
        """Set default limit if not provided."""
        if self.limit == 100:  # Default from Pagination model
            self.limit = DEFAULT_RESULTS
        return self


def normalize_key(key: str) -> str:
    """Normalize the subject key by converting to lowercase.

    Mirrors the behavior from subjects_json.normalize_key()
    """
    return key.lower()


def process_key(key: str) -> str:
    """Process the subject key.

    Base implementation from subjects_json.process_key().
    Subclasses (languages, publishers) override this.
    """
    return key


@router.get("/subjects/{key:path}.json")
async def subject_json(
    request: Request,
    key: str,
    params: Annotated[SubjectRequestParams, Depends()],
) -> dict[str, Any]:
    """
    Get subject information including works and optional facets.

    This endpoint provides data about a subject including:
    - Basic subject metadata (key, name, work_count)
    - List of works (with pagination)
    - Optional facets (authors, subjects, places, people, times, publishers, languages, publishing_history)
    """
    # Validate limit
    if params.limit > MAX_RESULTS:
        raise HTTPException(
            status_code=400,
            detail={"error": f"Specified limit exceeds maximum of {MAX_RESULTS}."},
        )
    # The key from the URL path is just the subject identifier (e.g., "love", "person:mark_twain")
    # We need to prepend "/subjects/" to match what get_subject() expects
    full_key = f"/subjects/{key}"

    # Normalize the key (lowercase conversion)
    nkey = normalize_key(full_key)

    # For the base subjects endpoint, normalize_key is just lowercase
    # If the key changed (e.g., due to case differences), we don't redirect in FastAPI
    # (web.py does, but we'll just use the normalized version)
    full_key = nkey

    # Process the key (base implementation does nothing, subclasses override)
    full_key = process_key(full_key)

    # Build filters
    filters: dict[str, str] = {}
    if params.has_fulltext == "true":
        filters["has_fulltext"] = "true"

    if publish_year_filter := date_range_to_publish_year_filter(
        params.published_in or ""
    ):
        filters["publish_year"] = publish_year_filter

    # Call get_subject (sync for now, as requested)
    # Note: This is a synchronous call within an async endpoint
    # We can make this truly async later by converting get_subject
    subject: Subject = get_subject(
        full_key,
        offset=params.offset or 0,
        limit=params.limit,
        sort=params.sort,
        details=params.details == "true",
        request_label="SUBJECT_ENGINE_API",
        **filters,
    )

    # Convert Subject object (web.storage) to dict
    # get_subject() already populates all fields including facets when details=True
    subject_results = dict(subject)

    # Handle ebook_count special case
    if params.has_fulltext == "true":
        subject_results["ebook_count"] = subject_results["work_count"]

    # Convert works (list of web.storage) to list of dicts
    subject_results["works"] = [dict(w) for w in subject.works]

    return subject_results
