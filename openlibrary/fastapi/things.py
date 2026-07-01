"""FastAPI endpoint for serving thing documents as JSON.

This file is named things.py because it handles the
generic "view document as JSON" pattern for multiple thing types —
works, editions/books, authors, and people (users).  The shared helpers
(``_entity_get`` / ``_entity_put``) and factory functions live here so
that every thing type gets identical behavior — JSONP support, revision
fetching, error formatting — without duplicating code.

Naming rationale
~~~~~~~~~~~~~~~~
The FastAPI router files in this package are named after the **route
domain** they serve (books.py → /api/books, lists.py → /lists/...,
subjects.py → /subjects/..., etc.).  A file called ``works.py`` that
also registers routes under ``/books/``, ``/authors/`` and ``/people/``
would be misleading.  ``things.py`` accurately captures the scope:
any top-level Open Library thing whose raw JSON document should be
exposed at ``/{type}/{id}.json``.
"""

import json
import re
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Path, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, Response

from infogami.infobase import client
from openlibrary.fastapi.auth import ApiPermissionsDep  # noqa: TC001
from openlibrary.fastapi.models import wrap_jsonp
from openlibrary.utils.request_context import site

router = APIRouter(tags=["things"])


# Shared query-parameter descriptors used by both factory and direct handlers.

#: ``?m=history`` routes to the version-history endpoint.
# NB: ``default`` is omitted here because the default is set via ``= None``
# in the function signature — FastAPI/Annotated rejects duplicate defaults.
_MODE_PARAM = Query(description="View mode. Set to ``history`` to return version history instead of the thing document.")

#: History pagination.
_HISTORY_AUTHOR = Query(description="Filter version history by author key (e.g. ``/people/openlibrary``).")
_HISTORY_OFFSET = Query(ge=0, description="Number of revisions to skip.")
_HISTORY_LIMIT = Query(ge=1, le=1000, description="Maximum revisions to return.")


# -------------------------------------------------------------------------
# Response models used for OpenAPI schema generation
# -------------------------------------------------------------------------
# The handlers return ``Response`` objects directly (to support JSONP), so
# FastAPI uses these models *only* for OpenAPI docs — the actual response
# payload is not validated or filtered through them.


class EntityRef(BaseModel):
    """A reference to another thing document (e.g. ``{"key": "/authors/OL1A"}``)."""

    key: str


class DatetimeValue(BaseModel):
    """An Open Library datetime sub-document."""

    type: Literal["/type/datetime"] = "/type/datetime"
    value: str


class BaseEntity(BaseModel):
    """Common metadata fields present in every thing document."""

    key: str
    type: EntityRef
    revision: int
    latest_revision: int
    created: DatetimeValue
    last_modified: DatetimeValue

    model_config = {"extra": "allow"}


class TextBlock(BaseModel):
    """An Open Library text sub-document (``{"type": "/type/text", "value": "..."}``)."""

    type: Literal["/type/text"] = "/type/text"
    value: str


class Link(BaseModel):
    """An Open Library link sub-document."""

    url: str
    title: str
    type: EntityRef = Field(default=EntityRef(key="/type/link"))


class WorkResponse(BaseEntity):
    """Full JSON of a work."""

    title: str = Field(default="", description="The work title.")
    subtitle: str | None = Field(default=None, description="The work subtitle.")
    authors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of author contributions (each entry is a dict with ``author``, ``type``, etc.).",
    )
    covers: list[int] | None = Field(default=None, description="List of cover image IDs.")
    links: list[Link] | None = Field(default=None, description="List of related links.")
    lc_classifications: list[str] | None = Field(default=None, description="Library of Congress classifications.")
    subjects: list[str] | None = Field(default=None, description="List of subject headings.")
    first_publish_date: str | None = Field(default=None, description="The first publication date.")
    description: TextBlock | str | None = Field(default=None, description="A description of the work.")
    notes: TextBlock | str | None = Field(default=None, description="Notes about the work.")


class EditionResponse(BaseEntity):
    """Full JSON of an edition (book)."""

    title: str = Field(default="", description="The edition title.")
    subtitle: str | None = Field(default=None, description="The edition subtitle.")
    works: list[EntityRef] = Field(
        default_factory=list,
        description="List of works this edition belongs to.",
    )
    authors: list[dict[str, Any]] | None = Field(
        default=None,
        description="List of authors.",
    )
    identifiers: dict[str, Any] | None = Field(default=None, description="External identifiers.")
    isbn_10: list[str] | None = Field(default=None, description="ISBN-10 numbers.")
    isbn_13: list[str] | None = Field(default=None, description="ISBN-13 numbers.")
    lccn: list[str] | None = Field(
        default=None,
        description="Library of Congress Control Numbers.",
    )
    ocaid: str | None = Field(
        default=None,
        description="Internet Archive OCAID.",
    )
    oclc_numbers: list[str] | None = Field(default=None, description="OCLC/WorldCat numbers.")
    local_id: list[str] | None = Field(default=None, description="Local identifiers.")
    covers: list[int] | None = Field(default=None, description="List of cover image IDs.")
    links: list[Link] | None = Field(default=None, description="List of related links.")
    languages: list[dict[str, Any]] | None = Field(default=None, description="List of languages.")
    translated_from: list[dict[str, Any]] | None = Field(default=None, description="Languages translated from.")
    translation_of: str | None = Field(default=None, description="The title of the original language work.")
    by_statement: str | None = Field(default=None, description="The by-statement credit.")
    weight: str | None = Field(default=None, description="The physical weight.")
    edition_name: str | None = Field(default=None, description="The edition name.")
    number_of_pages: int | None = Field(default=None, description="Number of pages.")
    pagination: str | None = Field(default=None, description="Pagination string.")
    physical_dimensions: str | None = Field(default=None, description="Physical dimensions.")
    physical_format: str | None = Field(default=None, description="Physical format (e.g. Paperback).")
    copyright_date: str | None = Field(default=None, description="Copyright date.")
    publish_country: str | None = Field(default=None, description="MARC country code.")
    publish_date: str | None = Field(default=None, description="Publication date in EDTF format.")
    publish_places: list[str] | None = Field(default=None, description="List of publication places.")
    publishers: list[str] | None = Field(default=None, description="List of publishers.")
    contributions: list[str] | None = Field(default=None, description="List of contributors.")
    dewey_decimal_class: list[str] | None = Field(default=None, description="Dewey Decimal classifications.")
    genres: list[str] | None = Field(default=None, description="List of genres.")
    lc_classifications: list[str] | None = Field(default=None, description="Library of Congress classifications.")
    other_titles: list[str] | None = Field(default=None, description="Other titles.")
    series: list[str] | None = Field(default=None, description="Series information.")
    source_records: list[str] | None = Field(default=None, description="Source record identifiers.")
    subjects: list[str] | None = Field(default=None, description="List of subject headings.")
    work_titles: list[str] | None = Field(default=None, description="Work titles.")
    table_of_contents: list[dict[str, Any]] | None = Field(default=None, description="Table of contents entries.")
    description: TextBlock | str | None = Field(default=None, description="A description of the edition.")
    first_sentence: TextBlock | str | None = Field(default=None, description="The first sentence.")
    notes: TextBlock | str | None = Field(default=None, description="Notes about the edition.")


class AuthorResponse(BaseEntity):
    """Full JSON of an author."""

    name: str = Field(default="", description="The author's display name.")
    alternate_names: list[str] | None = Field(default=None, description="Alternate names.")
    bio: TextBlock | str | None = Field(default=None, description="Biographical information.")
    birth_date: str | None = Field(default=None, description="Birth date.")
    death_date: str | None = Field(default=None, description="Death date.")
    date: str | None = Field(default=None, description="A date associated with the author.")
    entity_type: str | None = Field(default=None, description="Entity type (person, org, event).")
    fuller_name: str | None = Field(default=None, description="Fuller name.")
    personal_name: str | None = Field(default=None, description="Personal name.")
    title: str | None = Field(default=None, description="Title (e.g. Sir, Dr.).")
    photos: list[int] | None = Field(default=None, description="List of photo IDs.")
    links: list[Link] | None = Field(default=None, description="List of related links.")
    remote_ids: dict[str, str] | None = Field(default=None, description="Remote identifiers (wikidata, viaf, etc.).")


class UserResponse(BaseEntity):
    """Full JSON of a user profile."""

    displayname: str | None = Field(default=None, description="The user's display name.")


class PutResponse(BaseModel):
    """Response from saving a thing."""

    key: str = Field(description="The key of the saved thing.")
    revision: int = Field(ge=1, description="The new revision number.")


# -------------------------------------------------------------------------
# Internal helpers shared by all thing-type routes
# -------------------------------------------------------------------------


def _safe_client_error_status(e: client.ClientException) -> int:
    """Extract an HTTP status code from a ClientException status string."""
    try:
        match = re.search(r"\d{3}", e.status or "500")
        return int(match.group(0)) if match else 500
    except ValueError, TypeError:
        return 500


def _entity_history(
    key: str,
    author: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Fetch version history for a thing, stripping IP addresses.

    Mirrors the legacy web.py ``?m=history`` handler
    (``openlibrary.plugins.upstream.code.history``) which redacts IPs
    from the infobase version data before returning it.
    """
    query: dict[str, Any] = {"key": key, "sort": "-created", "offset": offset, "limit": limit}
    if author:
        query["author"] = author

    s = site.get()
    # Low-level connection mirrors ``infogami.plugins.api.code.request``.
    result = s._conn.request(s.name, "/versions", "GET", {"query": json.dumps(query)})
    history = json.loads(result)
    for row in history:
        row.pop("ip", None)
    return history


def _entity_get(
    request: Request,
    key: str,
    revision: int | None,
    text: bool,
) -> Response:
    """Shared GET logic: fetch a single thing by key and return JSON."""
    s = site.get()

    try:
        thing = s.get(key, revision=revision)
    except client.ClientException as e:
        status_code = _safe_client_error_status(e)
        return JSONResponse(
            status_code=status_code,
            content={"error": "internal_error", "detail": str(e)},
        )

    if thing is None:
        return JSONResponse(
            status_code=404,
            content={"error": "notfound", "key": key},
        )

    data = thing.dict()
    json_string = json.dumps(data)

    # text/plain override for legacy compatibility
    callback = request.query_params.get("callback")
    if text and not callback:
        return Response(content=json_string, media_type="text/plain")

    # JSONP wrapping for ?callback=functionName
    return wrap_jsonp(request, json_string)


def _entity_put(
    request: Request,
    key: str,
    body: dict[str, Any],
) -> Response:
    """Shared PUT logic: save a thing by key and return the result."""
    s = site.get()

    # Ensure the key in the body matches the URL key
    body_key = body.get("key")
    if body_key and body_key != key:
        return JSONResponse(
            status_code=400,
            content={"error": "key_mismatch", "detail": f"Key in body ({body_key}) does not match URL ({key})"},
        )

    body["key"] = key

    comment = body.pop("_comment", None)

    try:
        result = s.save(body, comment=comment)
    except client.ClientException as e:
        status_code = _safe_client_error_status(e)
        return JSONResponse(
            status_code=status_code,
            content={"error": "save_failed", "detail": str(e)},
        )

    return wrap_jsonp(request, json.dumps(result))


def _make_get_handler(entity_name: str, key_fmt: Callable[[int], str]) -> Callable:
    """Factory that creates a GET handler for a specific thing type.

    Args:
        entity_name: Human-readable name ("work", "edition", "author").
        key_fmt: Function that takes the numeric ID and returns the full key
                 (e.g. ``lambda n: f"/works/OL{n}W"``).
    """
    # Create the Path descriptor here (outside the handler) so the f-string
    # is evaluated eagerly and not stored as an unresolved string reference
    # by ``from __future__ import annotations``.
    entity_id_path = Path(gt=0, description=f"The Open Library {entity_name} numeric ID.")

    def handler(
        request: Request,
        entity_id: Annotated[int, entity_id_path],
        v: Annotated[
            int | None,
            Query(
                alias="v",
                ge=1,
                description="Fetch a specific revision instead of the latest.",
            ),
        ] = None,
        text: Annotated[
            bool,
            Query(
                description="If true, returns the response with Content-Type: text/plain instead of application/json.",
            ),
        ] = False,
        m: Annotated[str | None, _MODE_PARAM] = None,
        author: Annotated[str | None, _HISTORY_AUTHOR] = None,
        offset: Annotated[int, _HISTORY_OFFSET] = 0,
        limit: Annotated[int, _HISTORY_LIMIT] = 20,
    ) -> Response:
        key = key_fmt(entity_id)
        if m == "history":
            data = _entity_history(key, author=author, offset=offset, limit=limit)
            return wrap_jsonp(request, json.dumps(data))
        return _entity_get(request, key, revision=v, text=text)

    return handler


def _make_put_handler(entity_name: str, key_fmt: Callable[[int], str]) -> Callable:
    """Factory that creates a PUT handler for a specific thing type."""
    entity_id_path = Path(gt=0, description=f"The Open Library {entity_name} numeric ID.")

    def handler(
        request: Request,
        entity_id: Annotated[int, entity_id_path],
        body: Annotated[
            dict[str, Any],
            Body(
                description="The full thing document as JSON. The ``_comment`` field is extracted and passed as the save comment.",
            ),
        ],
        _: ApiPermissionsDep,
    ) -> Response:
        return _entity_put(request, key_fmt(entity_id), body=body)

    return handler


# -------------------------------------------------------------------------
# Route definitions for each entity type
# -------------------------------------------------------------------------

# --- Works -----------------------------------------------------------

WORK_DESC = "Returns the full JSON of a work, including metadata, subjects, and authors."

router.add_api_route(
    "/works/OL{entity_id}W.json",
    _make_get_handler("work", lambda n: f"/works/OL{n}W"),
    methods=["GET"],
    description=WORK_DESC,
    response_model=WorkResponse,
    tags=["things"],
)
router.add_api_route(
    "/works/OL{entity_id}W.json",
    _make_put_handler("work", lambda n: f"/works/OL{n}W"),
    methods=["PUT"],
    description="Saves an updated work document. Requires write access (admin, API usergroup, or bot-flagged user).",
    response_model=PutResponse,
    tags=["things"],
)

# --- Books (editions) -------------------------------------------------

BOOK_DESC = "Returns the full JSON of an edition (book), including metadata, works, publishers, etc."

router.add_api_route(
    "/books/OL{entity_id}M.json",
    _make_get_handler("edition", lambda n: f"/books/OL{n}M"),
    methods=["GET"],
    description=BOOK_DESC,
    response_model=EditionResponse,
    tags=["things"],
)
router.add_api_route(
    "/books/OL{entity_id}M.json",
    _make_put_handler("edition", lambda n: f"/books/OL{n}M"),
    methods=["PUT"],
    description=("Saves an updated edition document. Requires write access (admin, API usergroup, or bot-flagged user)."),
    response_model=PutResponse,
    tags=["things"],
)

# --- Authors ---------------------------------------------------------

AUTHOR_DESC = "Returns the full JSON of an author, including name, bio, birth/death dates, etc."

router.add_api_route(
    "/authors/OL{entity_id}A.json",
    _make_get_handler("author", lambda n: f"/authors/OL{n}A"),
    methods=["GET"],
    description=AUTHOR_DESC,
    response_model=AuthorResponse,
    tags=["things"],
)
router.add_api_route(
    "/authors/OL{entity_id}A.json",
    _make_put_handler("author", lambda n: f"/authors/OL{n}A"),
    methods=["PUT"],
    description="Saves an updated author document. Requires write access (admin, API usergroup, or bot-flagged user).",
    response_model=PutResponse,
    tags=["things"],
)

# --- People (users) --------------------------------------------------
# People use human-readable keys (/people/username) rather than OL IDs.
# The web.py view mode handles this generically — any path works.


@router.get(
    "/people/{username}.json",
    response_model=UserResponse,
    description="Returns the full JSON of a user profile, including display name, permissions, etc.",
)
def user_json(
    request: Request,
    username: str,
    v: Annotated[
        int | None,
        Query(
            alias="v",
            ge=1,
            description="Fetch a specific revision instead of the latest.",
        ),
    ] = None,
    text: Annotated[
        bool,
        Query(
            description="If true, returns the response with Content-Type: text/plain instead of application/json.",
        ),
    ] = False,
    m: Annotated[str | None, _MODE_PARAM] = None,
    author: Annotated[str | None, _HISTORY_AUTHOR] = None,
    offset: Annotated[int, _HISTORY_OFFSET] = 0,
    limit: Annotated[int, _HISTORY_LIMIT] = 20,
) -> Response:
    """Get the full JSON representation of a user profile.

    Fetches the user document at ``/people/{username}`` and returns it as JSON.
    When ``?m=history`` is set, returns version history instead.
    """
    key = f"/people/{username}"
    if m == "history":
        data = _entity_history(key, author=author, offset=offset, limit=limit)
        return wrap_jsonp(request, json.dumps(data))
    return _entity_get(request, key, revision=v, text=text)
