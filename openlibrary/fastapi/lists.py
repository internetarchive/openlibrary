from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import Response

from openlibrary.plugins.openlibrary.lists import get_list

router = APIRouter()


def _get_list_or_404(key: str, raw: bool) -> dict:
    """Fetch a list by key and raise 404 if not found or deleted."""
    if not (lst := get_list(key, raw=raw)) or (not raw and lst.get("type", {}).get("key") == "/type/delete"):
        raise HTTPException(status_code=404, detail="List not found")
    return lst


@router.get("/people/{username}/lists/{list_id}.json")
def list_view_json_user(
    username: Annotated[str, Path(description="The patron's username")],
    list_id: Annotated[str, Path(description="The list OLID, e.g. OL123L", pattern=r"OL\d+L")],
    raw: Annotated[bool, Query(alias="_raw", description="Return raw database record")] = False,
) -> dict:
    """
    Returns JSON metadata for a user-owned list.

    Example: /people/mekBot/lists/OL123L.json
    """
    key = f"/people/{username}/lists/{list_id}"
    return _get_list_or_404(key, raw=raw)


@router.get("/lists/{list_id}.json")
def list_view_json_public(
    list_id: Annotated[str, Path(description="The list OLID, e.g. OL456L", pattern=r"OL\d+L")],
    raw: Annotated[bool, Query(alias="_raw", description="Return raw database record")] = False,
) -> dict:
    """
    Returns JSON metadata for a public (non-user) list.

    Example: /lists/OL456L.json
    """
    key = f"/lists/{list_id}"
    return _get_list_or_404(key, raw=raw)


@router.get("/series/{list_id}.json")
def list_view_json_series(
    list_id: Annotated[str, Path(description="The series OLID, e.g. OL789L", pattern=r"OL\d+L")],
    raw: Annotated[bool, Query(alias="_raw", description="Return raw database record")] = False,
) -> dict:
    """
    Returns JSON metadata for a series.

    Example: /series/OL789L.json
    """
    key = f"/series/{list_id}"
    return _get_list_or_404(key, raw=raw)


# ---------------------------------------------------------------------------
# Stubs — other contributors' endpoints (not yet implemented)
# ---------------------------------------------------------------------------


async def lists_delete(filename: Annotated[str, Path()]) -> Response:
    return Response(status_code=200)


async def lists_json():
    pass


async def list_seeds():
    pass


async def list_editions_json():
    pass


async def list_subjects_json():
    pass
