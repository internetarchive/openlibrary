"""FastAPI Books API endpoints."""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Annotated, Any, Literal

import web
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, BeforeValidator, Field, RootModel

from openlibrary.fastapi.models import parse_comma_separated_list, wrap_jsonp
from openlibrary.plugins.books import dynlinks, readlinks

router = APIRouter()


class BooksAPIQueryParams(BaseModel):
    """Query parameters for Books API endpoint."""

    bibkeys: Annotated[list[str], BeforeValidator(parse_comma_separated_list)] = Field(
        ...,
        description="Comma-separated list of bibliography keys (ISBN, LCCN, OCLC, etc.)",
    )
    details: Literal["true", "false"] = Field("false", description="Include detailed book information")
    jscmd: Literal["details", "data", "viewapi"] | None = Field(None, description="Format of returned data")
    high_priority: bool = Field(False, description="Attempt import immediately for missing ISBNs")


class BookEntry(BaseModel):
    """Individual book entry in the Books API response."""

    bib_key: str = Field(..., description="The bibliography key (ISBN, LCCN, etc.)")
    info_url: str = Field(..., description="URL to the book's Open Library page")
    preview: Literal["noview", "free", "restricted", "full"] = Field(..., description="Preview availability status")
    preview_url: str = Field(..., description="URL to access the preview")
    thumbnail_url: str | None = Field(None, description="Cover thumbnail URL")
    details: dict[str, Any] | None = Field(None, description="Full book details (when jscmd=details)")


class BooksAPIResponse(RootModel[dict[str, BookEntry]]):
    """Response model for the Books API endpoint."""


# For these endpoints we set the response model to dict, but we return a string if there is a JSONP callback specified
# because we wrap the result in JSONP.
@router.get("/api/books", response_model=BooksAPIResponse, response_model_exclude_none=True, include_in_schema=False)
@router.get("/api/books.json", response_model=BooksAPIResponse, response_model_exclude_none=True)
async def get_books(
    request: Request,
    params: Annotated[BooksAPIQueryParams, Query()],
) -> Any:
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
        "format": "json",
    }

    # TODO: we should be passing down BooksAPIQueryParams not creating options
    if params.details:
        options["details"] = params.details
    if params.jscmd:
        options["jscmd"] = params.jscmd
    if params.high_priority:
        options["high_priority"] = params.high_priority

    # Call existing business logic (bibkeys already parsed by validator)
    result_str = dynlinks.dynlinks(bib_keys=params.bibkeys, options=options)
    return wrap_jsonp(request, json.loads(result_str))


MULTIGET_PATH_RE = re.compile(r"/api/volumes/(brief|full)/json/(.+)")


@router.get("/api/volumes/{brief_or_full}/json/{req}", response_model=dict, include_in_schema=False)
@router.get("/api/volumes/{brief_or_full}/json/{req}.json", response_model=dict)
async def get_volumes_multiget(
    request: Request,
    brief_or_full: Literal["brief", "full"],
    req: str,
) -> Any:
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
    return wrap_jsonp(request, result)


@router.get("/api/volumes/{brief_or_full}/{idtype}/{idval}", response_model=dict, include_in_schema=False)
@router.get("/api/volumes/{brief_or_full}/{idtype}/{idval}.json", response_model=dict)
async def get_volume(
    request: Request,
    brief_or_full: Literal["brief", "full"],
    idtype: Literal["oclc", "lccn", "issn", "isbn", "htid", "olid", "recordnumber"],
    idval: str,
    show_all_items: bool = Query(False, description="Show all items including restricted ones"),
) -> Any:
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
    result = result.get(req, [])
    return wrap_jsonp(request, result)
