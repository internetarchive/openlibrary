from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from openlibrary.fastapi.services.subject_service import (
    BaseSubjectRequestParams,
    fetch_subject_data,
)

router = APIRouter()


@router.get("/subjects/{key:path}.json", response_model=None)
async def subject_json(
    request: Request,
    key: str,
    params: Annotated[BaseSubjectRequestParams, Depends()],
) -> RedirectResponse | dict[str, Any]:
    """
    Get subject information including works and optional facets.

    This endpoint provides data about a subject including:
    - Basic subject metadata (key, name, work_count)
    - List of works (with pagination)
    - Optional facets (authors, subjects, places, people, times, publishers, languages, publishing_history)
    """
    # Normalize the key (lowercase)
    normalized_key = key.lower()

    # Handle old path patterns (temporary code from old implementation)
    # TODO: Determine if we still need this at all..
    if normalized_key.count("/") == 3:
        normalized_key = normalized_key.replace("/people/", "/person:")
        normalized_key = normalized_key.replace("/places/", "/place:")
        normalized_key = normalized_key.replace("/times/", "/time:")

    if normalized_key != key:
        return RedirectResponse(
            url=request.url.replace(path=f"/subjects/{normalized_key}.json"),
            status_code=301,
        )

    return fetch_subject_data(
        key=key,
        params=params,
        path_prefix="/subjects",
        normalize_key_func=lambda k: k.lower(),
    )
