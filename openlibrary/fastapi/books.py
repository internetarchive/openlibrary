"""FastAPI Books API endpoints."""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Annotated, Literal

import web
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, BeforeValidator, Field

from openlibrary.fastapi.models import parse_comma_separated_list
from openlibrary.plugins.books import dynlinks, readlinks

router = APIRouter()


class BooksAPIQueryParams(BaseModel):
    """Query parameters for Books API endpoint."""

    bibkeys: Annotated[list[str], BeforeValidator(parse_comma_separated_list)] = Field(
        ...,
        description="Comma-separated list of bibliography keys (ISBN, LCCN, OCLC, etc.)",
    )
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


MULTIGET_PATH_RE = re.compile(r"/api/volumes/(brief|full)/json/(.+)")


@router.get("/api/volumes/{brief_or_full}/json/{req}.json")
async def get_volumes_multiget(
    request: Request,
    brief_or_full: Literal["brief", "full"],
    req: str,
) -> dict:
    """
    Get volume information for multiple identifiers.

    This endpoint handles multi-lookup form of Hathi-style API,
    allowing multiple identifiers in a single request.

    Example:
        GET /api/volumes/brief/json/isbn:059035342X|oclc:123456.json
    """
    web.ctx.home = f"{request.url.scheme}://{request.url.netloc}"

    raw_uri = request.url.path

    decoded_path = urllib.parse.unquote(raw_uri)

    m = MULTIGET_PATH_RE.match(decoded_path)
    if not m or len(m.groups()) != 2:
        return {}

    _brief_or_full, req = m.groups()

    result = readlinks.readlinks(req, {})
    return result


@router.get("/api/volumes/{brief_or_full}/{idtype}/{idval}.json")
async def get_volume(
    request: Request,
    brief_or_full: Literal["brief", "full"],
    idtype: Literal["oclc", "lccn", "issn", "isbn", "htid", "olid", "recordnumber"],
    idval: str,
    show_all_items: bool = Query(
        False, description="Show all items including restricted ones"
    ),
) -> dict | list:
    """
    Get volume information by identifier type and value.

    This endpoint provides detailed information about a specific volume,
    modeled after HathiTrust Bibliographic API. Includes information
    about loans and other editions of same work.

    Example:
        GET /api/volumes/brief/isbn/059035342X.json
    """
    # Set up web context for readlinks compatibility
    # This ensures web.ctx.get("home") returns correct base URL
    web.ctx.home = f"{request.url.scheme}://{request.url.netloc}"

    # Build request identifier
    req = f"{idtype}:{idval}"

    # Build options dict from query parameters
    options: dict[str, str | bool] = {}
    if show_all_items:
        options["show_all_items"] = show_all_items

    # Call existing business logic
    result = readlinks.readlinks(req, options)

    # Return the result for this specific request key
    return result.get(req, [])
