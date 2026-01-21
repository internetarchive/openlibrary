from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from openlibrary.fastapi.services.subject_service import (
    BaseSubjectRequestParams,
    fetch_subject_data,
)

router = APIRouter()


class PublisherRequestParams(BaseSubjectRequestParams):
    """Query parameters for /publishers/{key}.json endpoint."""

    pass


def normalize_key(key: str) -> str:
    """Normalize the publisher key.

    Mirrors the behavior from publishers_json.normalize_key() - returns key as-is.
    """
    return key


def process_key(key: str) -> str:
    """Process the publisher key.

    Mirrors the behavior from publishers_json.process_key() - replaces underscores with spaces.
    """
    return key.replace("_", " ")


@router.get("/publishers/{key:path}.json")
async def publisher_json(
    key: str,
    params: Annotated[PublisherRequestParams, Depends()],
) -> dict[str, Any]:
    """
    Get publisher information including works and optional facets.

    This endpoint provides data about a publisher including:
    - Basic publisher metadata (key, name, work_count)
    - List of works (with pagination)
    - Optional facets (authors, subjects, places, people, times, publishers, languages, publishing_history)
    """
    return fetch_subject_data(
        key=key,
        params=params,
        path_prefix="/publishers",
        normalize_key_func=normalize_key,
        process_key_func=process_key,
    )
