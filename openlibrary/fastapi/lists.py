from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response

if TYPE_CHECKING:
    from fastapi.datastructures import URL

from infogami.infobase import client
from openlibrary.accounts import get_current_user
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.plugins.openlibrary.lists import get_list, get_list_editions
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


def _get_editions_response(request_url: URL, key: str, limit: int, offset: int) -> Response:
    """
    Helper function to fetch list or series editions and return them as a JSON-friendly dict.
    Utilizes the underlying `get_list_editions` method to ensure consistent behavior
    with the legacy API, passing the FastAPI `request.url` for pagination link generation.
    """
    response_data = get_list_editions(key=key, offset=offset, limit=limit, api=True, request_url=request_url)
    if not response_data:
        raise HTTPException(status_code=404, detail="Editions not found")

    return response_data


class EditionsPaginationParams:
    """Shared dependency for parsing limit, offset, and the request object."""

    def __init__(
        self,
        request: Request,
        limit: Annotated[int, Query(ge=1, description="Number of items to return")] = 50,
        offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    ):
        self.request = request
        self.limit = limit
        self.offset = offset


CommonPagination = Annotated[EditionsPaginationParams, Depends()]


@router.get("/lists/{olid}/editions.json")
def read_list_editions(
    olid: Annotated[str, Path(pattern=r"^OL\d+L$", description="The list or series OLID")],
    params: CommonPagination,
):
    """
    Get paginated editions for a public list.
    """
    key = f"/lists/{olid}"
    return _get_editions_response(params.request.url, key, params.limit, params.offset)


@router.get("/people/{username}/lists/{olid}/editions.json")
def read_people_list_editions(
    username: Annotated[str, Path()],
    olid: Annotated[str, Path(pattern=r"^OL\d+L$", description="The list or series OLID")],
    params: CommonPagination,
):
    """
    Get paginated editions for a specific user's list.
    """
    key = f"/people/{username}/lists/{olid}"
    return _get_editions_response(params.request.url, key, params.limit, params.offset)


@router.get("/series/{olid}/editions.json")
def read_series_editions(
    olid: Annotated[str, Path(pattern=r"^OL\d+L$", description="The list or series OLID")],
    params: CommonPagination,
):
    """
    Get paginated editions for a specific series.
    """
    key = f"/series/{olid}"
    return _get_editions_response(params.request.url, key, params.limit, params.offset)


@router.get("/people/{username}/series/{olid}/editions.json")
def read_people_series_editions(
    username: Annotated[str, Path()],
    olid: Annotated[str, Path(pattern=r"^OL\d+L$", description="The list or series OLID")],
    params: CommonPagination,
):
    """
    Get paginated editions for a specific user's series.
    """
    key = f"/people/{username}/series/{olid}"
    return _get_editions_response(params.request.url, key, params.limit, params.offset)


async def list_subjects_json():
    pass
