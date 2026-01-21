from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from openlibrary.core.models import Subject
from openlibrary.fastapi.models import Pagination
from openlibrary.plugins.worksearch.languages import get_top_languages
from openlibrary.plugins.worksearch.subjects import (
    DEFAULT_RESULTS,
    MAX_RESULTS,
    date_range_to_publish_year_filter,
    get_subject,
)


class Language(BaseModel):
    name: str
    key: str
    marc_code: str
    count: int
    ebook_edition_count: int


router = APIRouter()


@router.get("/languages.json", response_model=list[Language])
async def list_languages(
    request: Request,
    sort: Literal["count", "name", "ebook_edition_count"] = Query(
        "count", description="The field to sort by."
    ),
    limit: int = Query(15, gt=0, description="The max number of results to return."),
):
    """
    Get a list of the top languages, sorted by the specified criteria.
    """
    return await get_top_languages(limit=limit, user_lang=request.state.lang, sort=sort)


class LanguageRequestParams(Pagination):
    """Query parameters for /languages/{key}.json endpoint."""

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
    limit: int = Field(
        DEFAULT_RESULTS,
        ge=0,
        le=MAX_RESULTS,
        description="The max number of results to return.",
    )


def normalize_key(key: str) -> str:
    """Normalize the publisher key.

    Mirrors the behavior from publishers_json.normalize_key() - returns key as-is.
    """
    return key


def process_key(key: str) -> str:
    """Process the language key.

    Mirrors the behavior from languages_json.process_key() - replaces underscores with spaces.
    """
    return key.replace("_", " ")


@router.get("/languages/{key:path}.json")
async def language_json(
    request: Request,
    key: str,
    params: Annotated[LanguageRequestParams, Depends()],
) -> dict[str, Any]:
    """
    Get language information including works and optional facets.

    This endpoint provides data about a language including:
    - Basic language metadata (key, name, work_count)
    - List of works (with pagination)
    - Optional facets (authors, subjects, places, people, times, publishers, languages, publishing_history)
    """

    # The key from the URL path is just the language identifier (e.g., "english_language")
    # We need to prepend "/languages/" to match what get_subject() expects
    full_key = f"/languages/{key}"

    # Normalize the key (publishers don't normalize - no lowercase)
    nkey = normalize_key(full_key)
    full_key = nkey

    # Process the key (replace underscores with spaces)
    full_key = process_key(full_key)

    # Build filters
    filters: dict[str, str] = {}
    if params.has_fulltext == "true":
        filters["has_fulltext"] = "true"

    if publish_year_filter := date_range_to_publish_year_filter(
        params.published_in or ""
    ):
        filters["publish_year"] = publish_year_filter

    # Call get_subject (sync for now)
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
