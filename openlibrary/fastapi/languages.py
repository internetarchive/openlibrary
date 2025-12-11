from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request

from openlibrary.plugins.worksearch.languages import get_top_languages

router = APIRouter()


@router.get("/languages.json")
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
