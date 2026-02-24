"""FastAPI Books API endpoints."""

from __future__ import annotations

import json
from typing import Annotated, Literal

import web
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, BeforeValidator, Field

from openlibrary.fastapi.models import parse_comma_separated_list
from openlibrary.plugins.books import dynlinks

router = APIRouter()


class BooksAPIQueryParams(BaseModel):
    """Query parameters for Books API endpoint."""

    bibkeys: Annotated[list[str], BeforeValidator(parse_comma_separated_list)] = Field(
        ...,
        description="Comma-separated list of bibliography keys (ISBN, LCCN, OCLC, etc.)",
    )
    callback: str | None = Field(None, description="JSONP callback function name")
    details: Literal["true", "false"] = Field(
        "false", description="Include detailed book information"
    )
    jscmd: Literal["details", "data", "viewapi"] | None = Field(
        None, description="Format of returned data"
    )
    high_priority: bool = Field(
        False, description="Attempt import immediately for missing ISBNs"
    )


@router.get("/api/books.json")
async def get_books(
    request: Request,
    params: Annotated[BooksAPIQueryParams, Query()],
) -> dict:
    """
    Get book metadata by bibliography keys.

    This endpoint provides basic information about books, including URLs,
    thumbnail links, and preview availability. Supports ISBNs, LCCNs,
    OCLC numbers, and Open Library IDs.

    When `high_priority=true`, API will attempt to import editions
    from ISBNs that don't exist in database immediately, rather
    than queueing them for later lookup.
    """

    # Set up web context for dynlinks compatibility
    # This ensures web.ctx.get("home") returns correct base URL
    web.ctx.home = f"{request.url.scheme}://{request.url.netloc}"

    # Build options dict compatible with existing dynlinks function
    options: dynlinks.DynlinksOptions = {
        'format': 'json',
    }

    # TODO: we should be passing down BooksAPIQueryParams not creating options
    if params.callback:
        options['callback'] = params.callback
    if params.details:
        options['details'] = params.details
    if params.jscmd:
        options['jscmd'] = params.jscmd
    if params.high_priority:
        options['high_priority'] = params.high_priority

    # Call existing business logic (bibkeys already parsed by validator)
    result_str = dynlinks.dynlinks(bib_keys=params.bibkeys, options=options)

    # Parse and return JSON result (direct dict to match exact old format)
    return json.loads(result_str)
