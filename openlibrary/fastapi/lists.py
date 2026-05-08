from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import Response

import openlibrary.core.helpers as h
from infogami.infobase import client
from openlibrary.core import formats
from openlibrary.plugins.openlibrary import lists as legacy_lists
from openlibrary.utils.request_context import site

router = APIRouter()
get_list = legacy_lists.get_list


def _get_list_or_404(key: str, raw: bool) -> dict:
    """Fetch a list by key and raise 404 if not found or deleted."""
    if not (lst := get_list(key, raw=raw)) or lst.get("type", {}).get("key") == "/type/delete":
        raise HTTPException(status_code=404, detail="List not found")
    return lst


UsernamePath = Annotated[str, Path(description="The patron's username")]
RawFlag = Annotated[bool, Query(alias="_raw", description="Return raw database record")]
ListOLID = Annotated[str, Path(description="The OLID, e.g. OL123L", pattern=r"OL\d+L")]
ListCategory = Annotated[Literal["lists", "series"], Path(description="List category")]


@router.get("/people/{username}/{category}/{list_id}.json")
def list_view_json_user(
    username: UsernamePath,
    category: ListCategory,
    list_id: ListOLID,
    raw: RawFlag = False,
) -> dict:
    """
    Returns JSON metadata for a user-owned list or series.

    Examples:
    /people/mekBot/lists/OL123L.json
    /people/mekBot/series/OL123L.json
    """
    key = f"/people/{username}/{category}/{list_id}"
    return _get_list_or_404(key, raw=raw)


@router.get("/{category}/{list_id}.json")
def list_view_json_public(
    category: ListCategory,
    list_id: ListOLID,
    raw: RawFlag = False,
) -> dict:
    """
    Returns JSON metadata for a public list or series.

    Examples:
    /lists/OL456L.json
    /series/OL789L.json
    """
    key = f"/{category}/{list_id}"
    return _get_list_or_404(key, raw=raw)


async def lists_delete(filename: Annotated[str, Path()]) -> Response:
    return Response(status_code=200)


async def _raw_body(request: Request) -> bytes:
    return await request.body()


def _json_response(data, status_code: int = 200) -> Response:
    return Response(
        content=formats.dump(data, "json"),
        media_type="application/json",
        status_code=status_code,
    )


def _status_code(status: int | str) -> int:
    if isinstance(status, int):
        return status
    return int(str(status).split()[0])


def _lists_seed_path(
    username: str | None = None,
    edition_id: int | None = None,
    work_id: int | None = None,
    author_id: int | None = None,
    subject_key: str | None = None,
) -> str:
    if username is not None:
        return f"/people/{username}"
    if edition_id is not None:
        return f"/books/OL{edition_id}M"
    if work_id is not None:
        return f"/works/OL{work_id}W"
    if author_id is not None:
        return f"/authors/OL{author_id}A"
    if subject_key is not None:
        return f"/subjects/{subject_key}"
    raise ValueError("Could not determine lists path")


def _request_query(request: Request):
    return {
        key: values[0] if len(values) == 1 else values
        for key, values in parse_qs(
            request.url.query,
            keep_blank_values=True,
        ).items()
    }


@router.get("/people/{username}/lists.json")
@router.get("/books/OL{edition_id}M/lists.json")
@router.get("/works/OL{work_id}W/lists.json")
@router.get("/authors/OL{author_id}A/lists.json")
@router.get("/subjects/{subject_key:path}/lists.json")
def lists_json(
    request: Request,
    username: str | None = None,
    edition_id: int | None = None,
    work_id: int | None = None,
    author_id: int | None = None,
    subject_key: str | None = None,
):
    offset = h.safeint(request.query_params.get("offset", 0), 0)
    limit = h.safeint(request.query_params.get("limit", 50), 50)

    limit = min(limit, 100)
    offset = max(offset, 0)

    seed_path = _lists_seed_path(
        username=username,
        edition_id=edition_id,
        work_id=work_id,
        author_id=author_id,
        subject_key=subject_key,
    )
    current_site = site.get()
    data = legacy_lists.get_lists_json_data(
        seed_path,
        current_site,
        limit=limit,
        offset=offset,
        query=_request_query(request),
        query_path=request.url.path,
    )
    if data is None:
        return Response(status_code=404)
    return _json_response(data)


@router.post("/people/{username}/lists.json")
def lists_json_post(
    username: str,
    body: Annotated[bytes, Depends(_raw_body)],
):
    current_site = site.get()
    user_key = f"/people/{username}"
    user = current_site.get(user_key)

    if not user:
        return Response(status_code=404)

    if not current_site.can_write(user_key):
        return _json_response({"message": "Permission denied."}, status_code=403)

    data = formats.load(body, "json")

    try:
        result = legacy_lists.lists_json.process_new_list(user, data, current_site)
    except ValueError as e:
        if str(e) == "Spam list":
            return _json_response({"message": "Permission denied."}, status_code=403)
        raise
    except client.ClientException as e:
        return _json_response(
            {"message": str(e)},
            status_code=_status_code(e.status),
        )

    return _json_response(result)


async def list_seeds():
    pass


async def list_editions_json():
    pass


async def list_subjects_json():
    pass
