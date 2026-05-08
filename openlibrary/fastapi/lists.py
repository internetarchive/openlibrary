from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import Response

from openlibrary.plugins.openlibrary.lists import get_list, get_list_subjects

router = APIRouter()


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


async def lists_json():
    pass


async def list_seeds():
    pass


async def list_editions_json():
    pass


@router.get("/people/{username}/lists/{list_id}/subjects.json")
def list_subjects_json_user(username: str, list_id: Annotated[str, Path(pattern=r"^OL[0-9]+L$")], limit: int = 20) -> dict:
    key = f"/people/{username}/lists/{list_id}"
    if data := get_list_subjects(key, limit):
        return data
    raise HTTPException(status_code=404, detail="List not found")


@router.get("/lists/{list_id}/subjects.json")
def list_subjects_json_public(list_id: Annotated[str, Path(pattern=r"^OL[0-9]+L$")], limit: int = 20) -> dict:
    key = f"/lists/{list_id}"
    if data := get_list_subjects(key, limit):
        return data
    raise HTTPException(status_code=404, detail="List not found")


@router.get("/series/{list_id}/subjects.json")
def list_subjects_json_series(list_id: Annotated[str, Path(pattern=r"^OL[0-9]+L$")], limit: int = 20) -> dict:
    key = f"/series/{list_id}"
    if data := get_list_subjects(key, limit):
        return data
    raise HTTPException(status_code=404, detail="List not found")
