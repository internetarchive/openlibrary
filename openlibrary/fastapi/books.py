"""FastAPI Books API endpoints.

DO NOT follow the example of this code... it is horrible and not following
the best practices like Response Models because JSONP makes it quite complicated.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Annotated, Any, Literal

import web
from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, BeforeValidator, Field, TypeAdapter

from openlibrary.fastapi.models import parse_comma_separated_list, wrap_jsonp
from openlibrary.plugins.books import dynlinks, readlinks
from openlibrary.plugins.books.dynlinks import DynlinksOptions

router = APIRouter()


class BooksAPIQueryParams(BaseModel):
    """Query parameters for Books API endpoint."""

    bibkeys: Annotated[list[str], BeforeValidator(parse_comma_separated_list)] = Field(
        ...,
        description="Comma-separated list of bibliography keys (ISBN, LCCN, OCLC, etc.)",
    )
    details: Literal["true", "false"] = Field("false", description="Include detailed book information")
    jscmd: Literal["details", "data", "viewapi"] | None = Field(None, description="Format of returned data")
    callback: str | None = Field(None, description="JSONP callback function name")
    high_priority: bool = Field(False, description="Attempt import immediately for missing ISBNs")
    format: Literal["json", "js"] | None = Field(None, description="Explicitly set response format (overrides path-based detection)")
    text: bool = Field(False, description="Return Content-Type: text/plain instead of application/json")


# Note: We don't set response_model on these endpoints because they support JSONP callback.
# When callback parameter is present, the function returns a Response object directly,
# which should bypass response model validation. Setting response_model on the decorator
# can interfere with Response object's content-type headers.
@router.get("/api/books", include_in_schema=False)
@router.get("/api/books.json")
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

    # Build options dict from params (excluding bibkeys which goes to dynlinks separately)
    options: DynlinksOptions = TypeAdapter(DynlinksOptions).validate_python(params.model_dump(exclude_unset=True))

    # Format determination priority:
    # 1. format parameter (highest)
    # 2. callback parameter (medium) - when present, overrides path-based format
    # 3. path-based detection (lowest)
    if not params.format:
        if params.callback:
            options["format"] = "js"
        elif request.url.path.endswith(".json"):
            options["format"] = "json"

    # Call existing business logic
    result_str = dynlinks.dynlinks(bib_keys=params.bibkeys, options=options)

    # If callback is present, wrap the JSON result with the callback
    # (dynlinks returns plain JSON when callback is in options, we need to wrap it)
    if params.callback is not None:
        result_str = f"{params.callback}({result_str});"

    # Content-Type is almost always application/json (matching production behavior)
    # Only changes to text/plain when text=true parameter is present
    media_type = "text/plain" if params.text else "application/json"

    return Response(content=result_str, media_type=media_type)


MULTIGET_PATH_RE = re.compile(r"/api/volumes/(brief|full)/json/(.+)")


@router.get("/api/volumes/{brief_or_full}/json/{req}", include_in_schema=False)
@router.get("/api/volumes/{brief_or_full}/json/{req}.json")
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


# Left without a strict response model since it can return either a VolumeResponse dict or an empty list [] for non-existent identifiers. Pydantic
# can't represent this union cleanly without losing validation benefits.
@router.get("/api/volumes/{brief_or_full}/{idtype}/{idval}", include_in_schema=False)
@router.get("/api/volumes/{brief_or_full}/{idtype}/{idval}.json")
async def get_volume(
    request: Request,
    brief_or_full: Literal["brief", "full"],
    idtype: Literal["oclc", "lccn", "issn", "isbn", "htid", "olid", "recordnumber"],
    idval: str,
    show_all_items: Annotated[bool, Query(description="Show all items including restricted ones")] = False,
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
