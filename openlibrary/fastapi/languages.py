from __future__ import annotations

import logging
from typing import Literal

import web
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from openlibrary.plugins.worksearch.languages import get_top_languages

logger = logging.getLogger("openlibrary.api")
router = APIRouter()


SortOptions = Literal["count", "name", "ebook_edition_count"]


# This can handle 5x as many requests without even using async at lower levels
@router.get("/_fast/languages.json", response_class=JSONResponse)
async def get_languages(limit: int = Query(15, gt=0), sort: SortOptions = "count"):
    """
    Get a list of top languages.
    """
    # TODO, this is an example of where we really need to dig in and replicate the web.py logic of getting lang
    # because it looks in three places: parse_query_string() or parse_lang_cookie() or parse_lang_header()
    web.ctx.lang = "en"
    return get_top_languages(limit=limit, sort=sort)
