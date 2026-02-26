"""Shared service layer for subject-type endpoints.

This module provides reusable functions and classes for handling
subject-type endpoints (subjects and publishers) to avoid
code duplication and ensure consistent behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from openlibrary.fastapi.models import Pagination
from openlibrary.plugins.worksearch.subjects import (
    DEFAULT_RESULTS,
    MAX_RESULTS,
    date_range_to_publish_year_filter,
    get_subject_async,
)

if TYPE_CHECKING:
    from openlibrary.core.models import Subject


class BaseSubjectRequestParams(Pagination):
    """Base query parameters for subject-type endpoints.

    This class defines common parameters used across subjects and publishers endpoints.
    """

    details: bool = Field(False, description="Include facets and detailed metadata")
    has_fulltext: bool = Field(False, description="Filter to works with fulltext")
    sort: str = Field(
        "editions", description="Sort order: editions, old, new, ranking, etc."
    )
    published_in: str | None = Field(
        None, description="Date range filter: YYYY or YYYY-YYYY"
    )
    limit: int = Field(
        DEFAULT_RESULTS,
        ge=0,
        le=MAX_RESULTS,
        description="The max number of results to return.",
    )


async def fetch_subject_data(
    key: str,
    params: BaseSubjectRequestParams,
    path_prefix: Literal["/subjects", "/publishers"],
) -> dict[str, Any]:
    """Fetch subject data and convert to dict format.

    This is the core business logic shared across all subject-type endpoints.

    Args:
        key: The subject key from the URL path
        params: The validated request parameters
        path_prefix: The URL path prefix (e.g., "/subjects", "/languages")

    Returns:
        Dictionary containing subject data with works list
    """
    # Build the full key by prepending the path prefix
    full_key = f"{path_prefix}/{key}"

    # Build filters from request parameters
    filters = {}
    if params.has_fulltext:
        filters["has_fulltext"] = "true"
    if publish_year_filter := date_range_to_publish_year_filter(
        params.published_in or ""
    ):
        filters["publish_year"] = publish_year_filter

    subject: Subject = await get_subject_async(
        full_key,
        offset=params.offset or 0,
        limit=params.limit,
        sort=params.sort,
        details=params.details,
        request_label="SUBJECT_ENGINE_API",
        **filters,
    )

    # Convert Subject object (web.storage) to dict
    subject_results = dict(subject)

    # Handle ebook_count special case
    if params.has_fulltext:
        subject_results["ebook_count"] = subject_results["work_count"]

    # Convert works (list of web.storage) to list of dicts
    subject_results["works"] = [dict(w) for w in subject.works]

    return subject_results
