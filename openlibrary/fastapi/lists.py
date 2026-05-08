from __future__ import annotations

from typing import Annotated, Literal

import web
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from infogami.infobase import client
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.plugins.openlibrary.lists import get_list
from openlibrary.plugins.openlibrary.lists import lists_delete as _LegacyListsDelete
from openlibrary.utils.request_context import site

router = APIRouter(tags=["lists"])


def _get_list_or_404(key: str, raw: bool) -> dict:
    """Fetch a list by key and raise 404 if not found or deleted."""
    if not (lst := get_list(key, raw=raw)) or lst.get("type", {}).get("key") == "/type/delete":
        raise HTTPException(status_code=404, detail="List not found")
    return lst


def _process_list_delete(key: str) -> dict:
    """Shared delete logic for both route variants."""

    if not site.get().can_write(key):
        raise HTTPException(status_code=403, detail="Permission denied.")

    doc = site.get().get(key)
    if doc is None or doc.type.key != "/type/list":
        raise HTTPException(status_code=404, detail="Not found.")

    try:
        had_site = "site" in web.ctx
        previous_site = web.ctx.get("site") if had_site else None
        web.ctx.site = site.get()
        try:
            _LegacyListsDelete.process_delete(doc, key)
        finally:
            if had_site:
                web.ctx.site = previous_site
            else:
                web.ctx.pop("site", None)
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


@router.post("/people/{username}/lists/{list_id}/delete.json")
def lists_delete(
    username: UsernamePath,
    list_id: ListOLID,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict:
    """Delete a list owned by the given user."""
    return _process_list_delete(f"/people/{username}/lists/{list_id}")


@router.post("/lists/{list_id}/delete.json")
def lists_delete_no_prefix(
    list_id: ListOLID,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict:
    """Delete a list (legacy path without username prefix)."""
    return _process_list_delete(f"/lists/{list_id}")


async def lists_json():
    pass


async def list_seeds():
    pass


async def list_editions_json():
    pass


async def list_subjects_json():
    pass
