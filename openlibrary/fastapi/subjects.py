from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from openlibrary.fastapi.services.subject_service import (
    BaseSubjectRequestParams,
    fetch_subject_data,
)

router = APIRouter()


@router.get("/subjects/{key:path}.json")
async def subject_json(
    request: Request,
    key: str,
    params: Annotated[BaseSubjectRequestParams, Depends()],
) -> dict[str, Any]:
    """
    Get subject information including works and optional facets.

    This endpoint provides data about a subject including:
    - Basic subject metadata (key, name, work_count)
    - List of works (with pagination)
    - Optional facets (authors, subjects, places, people, times, publishers, languages, publishing_history)
    """
    return fetch_subject_data(
        key=key,
        params=params,
        path_prefix="/subjects",
        normalize_key_func=lambda k: k.lower(),
    )
