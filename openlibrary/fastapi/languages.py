from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

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
    sort: Literal["count", "name", "ebook_edition_count"] = Query("count", description="The field to sort by."),
    limit: int = Query(15, gt=0, description="The max number of results to return."),
):
    """
    Get a list of the top languages, sorted by the specified criteria.
    """
    return await get_top_languages(limit=limit, user_lang=request.state.lang, sort=sort)
