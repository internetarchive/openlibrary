from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from openlibrary.fastapi.services.subject_service import (
    BaseSubjectRequestParams,
    fetch_subject_data,
)
from openlibrary.plugins.worksearch.languages import get_top_languages


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


@router.get("/languages/{key:path}.json")
async def language_json(
    key: str,
    params: Annotated[BaseSubjectRequestParams, Depends()],
) -> dict[str, Any]:
    """
    Get language information including works and optional facets.

    This endpoint provides data about a language including:
    - Basic language metadata (key, name, work_count)
    - List of works (with pagination)
    - Optional facets (authors, subjects, places, people, times, publishers, languages, publishing_history)
    """
    return fetch_subject_data(
        key=key,
        params=params,
        path_prefix="/languages",
        process_key_func=lambda k: k.replace("_", " "),
    )
