from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response

from openlibrary.core import formats
from openlibrary.utils.request_context import site

from infogami.infobase import client
from openlibrary.accounts import get_current_user
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.plugins.openlibrary.lists import get_list
from openlibrary.plugins.openlibrary.lists import lists_delete as _LegacyListsDelete
from openlibrary.utils.request_context import site, web_ctx_ip

router = APIRouter(tags=["lists"])


def _get_list_or_404(key: str, raw: bool) -> dict:
    """Fetch a list by key and raise 404 if not found or deleted."""
    if not (lst := get_list(key, raw=raw)) or lst.get("type", {}).get("key") == "/type/delete":
        raise HTTPException(status_code=404, detail="List not found")
    return lst


def _process_list_delete(key: str) -> dict:
    """Shared delete logic for both route variants."""

    user = get_current_user()

    if user and not user.is_admin() and (user.key and not key.startswith(user.key)):
        raise HTTPException(status_code=403, detail="Permission denied.")

    doc = site.get().get(key)
    if doc is None or doc.type.key != "/type/list":
        raise HTTPException(status_code=404, detail="Not found.")

    try:
        with web_ctx_ip():
            _LegacyListsDelete.process_delete(doc, key)
    except client.ClientException as e:
        raise HTTPException(
            status_code=int(e.status.split()[0]),
            detail=e.json.decode("utf-8") if isinstance(e.json, bytes) else e.json,
        )

    return {"status": "ok"}


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


@router.get("/lists/{list_id}.json")
@router.get("/series/{list_id}.json")
def list_view_json_public(
    request: Request,
    list_id: ListOLID,
    raw: RawFlag = False,
) -> dict:
    """
    Returns JSON metadata for a public list or series.

    Examples:
    /lists/OL456L.json
    /series/OL789L.json
    """
    category = request.url.path.split("/")[1]
    key = f"/{category}/{list_id}"
    return _get_list_or_404(key, raw=raw)


@router.post("/people/{username}/lists/{list_id}/delete.json")
def lists_delete(
    username: UsernamePath,
    list_id: ListOLID,
    _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict:
    """Delete a list owned by the given user."""
    return _process_list_delete(f"/people/{username}/lists/{list_id}")


@router.post("/lists/{list_id}/delete.json")
def lists_delete_no_prefix(
    list_id: ListOLID,
    _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict:
    """Delete a list (legacy path without username prefix)."""
    return _process_list_delete(f"/lists/{list_id}")


async def lists_json():
    pass


async def list_seeds():
    pass


def fastapi_make_collection(
    request: Request,
    size: int,
    entries: list,
    limit: int,
    offset: int,
    key: str | None = None,
) -> dict[str, Any]:
    def _get_relative_url(url: Any) -> str:
        return f"{url.path}?{url.query}" if url.query else url.path

    links: dict[str, str] = {
        "self": _get_relative_url(request.url),
    }

    d: dict[str, Any] = {
        "size": size,
        "start": offset,
        "end": offset + limit,
        "entries": entries,
        "links": links,
    }

    if offset + len(entries) < size:
        next_url = request.url.include_query_params(limit=limit, offset=offset + limit)
        links["next"] = _get_relative_url(next_url)

    if offset > 0:
        prev_url = request.url.include_query_params(limit=limit, offset=max(0, offset - limit))
        links["prev"] = _get_relative_url(prev_url)

    if key:
        links["list"] = key

    return d


def _get_editions_response(request: Request, key: str, ext: str, limit: int, offset: int) -> Response:
    lst = site.get().get(key)
    if not lst:
        raise HTTPException(status_code=404)

    all_editions = list(lst.get_editions())
    editions = all_editions[offset : offset + limit]

    response_data = fastapi_make_collection(
        request=request,
        size=len(all_editions),
        entries=[e.dict() for e in editions],
        limit=limit,
        offset=offset,
        key=key,
    )

    encoding: Literal["json", "yml"] = "yml" if ext in ("yml", "yaml") else "json"
    content_type = 'text/yaml; charset="utf-8"' if encoding == "yml" else "application/json"

    content = formats.dump(response_data, encoding)
    return Response(content=content, media_type=content_type)


@router.get("/lists/{olid}/editions.{ext}")
def read_list_editions(
    request: Request,
    olid: Annotated[str, Path(pattern=r"^OL\d+L$")],
    ext: Annotated[Literal["json", "yml", "yaml"], Path()],
    limit: Annotated[int, Query(ge=1, description="Number of editions to return")] = 50,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
):
    key = f"/lists/{olid}"
    return _get_editions_response(request, key, ext, limit, offset)


@router.get("/people/{username}/lists/{olid}/editions.{ext}")
def read_people_list_editions(
    request: Request,
    username: Annotated[str, Path()],
    olid: Annotated[str, Path(pattern=r"^OL\d+L$")],
    ext: Annotated[Literal["json", "yml", "yaml"], Path()],
    limit: Annotated[int, Query(ge=1)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    key = f"/people/{username}/lists/{olid}"
    return _get_editions_response(request, key, ext, limit, offset)


@router.get("/series/{olid}/editions.{ext}")
def read_series_editions(
    request: Request,
    olid: Annotated[str, Path(pattern=r"^OL\d+L$")],
    ext: Annotated[Literal["json", "yml", "yaml"], Path()],
    limit: Annotated[int, Query(ge=1)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    key = f"/series/{olid}"
    return _get_editions_response(request, key, ext, limit, offset)


@router.get("/people/{username}/series/{olid}/editions.{ext}")
def read_people_series_editions(
    request: Request,
    username: Annotated[str, Path()],
    olid: Annotated[str, Path(pattern=r"^OL\d+L$")],
    ext: Annotated[Literal["json", "yml", "yaml"], Path()],
    limit: Annotated[int, Query(ge=1)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    key = f"/people/{username}/series/{olid}"
    return _get_editions_response(request, key, ext, limit, offset)


async def list_subjects_json():
    pass
