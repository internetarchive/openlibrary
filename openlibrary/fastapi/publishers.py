from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from openlibrary.fastapi.services.subject_service import (
    BaseSubjectRequestParams,
    fetch_subject_data,
)

router = APIRouter()


@router.get("/publishers/{key:path}.json")
async def publisher_json(
    key: str,
    params: Annotated[BaseSubjectRequestParams, Depends()],
) -> dict[str, Any]:
    """
    Get publisher information including works and optional facets.

    This endpoint provides data about a publisher including:
    - Basic publisher metadata (key, name, work_count)
    - List of works (with pagination)
    - Optional facets (authors, subjects, places, people, times, publishers, languages, publishing_history)
    """
    return await fetch_subject_data(
        key=key,
        params=params,
        path_prefix="/publishers",
        process_key_func=lambda k: k.replace("_", " "),
    )
