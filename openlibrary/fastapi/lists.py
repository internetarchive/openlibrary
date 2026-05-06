from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from infogami.infobase import client
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.plugins.openlibrary.lists import lists_delete as _LegacyListsDelete
from openlibrary.utils.request_context import site

router = APIRouter()


def _process_list_delete(key: str) -> dict:
    """Shared delete logic for both route variants."""
    if not site.get().can_write(key):
        raise HTTPException(status_code=403, detail="Permission denied.")

    doc = site.get().get(key)
    if doc is None or doc.type.key != "/type/list":
        raise HTTPException(status_code=404, detail="Not found.")

    try:
        _LegacyListsDelete.process_delete(doc, key)
    except client.ClientException as e:
        raise HTTPException(status_code=int(e.status.split()[0]), detail=e.json)

    return {"status": "ok"}


@router.post(
    "/people/{username}/lists/{list_id}/delete.json",
    description="Delete a list owned by the given user.",
)
def lists_delete(
    username: Annotated[str, Path()],
    list_id: Annotated[str, Path(pattern=r"^OL\d+L$")],
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict:
    return _process_list_delete(f"/people/{username}/lists/{list_id}")


@router.post(
    "/lists/{list_id}/delete.json",
    description="Delete a list.",
)
def lists_delete_no_prefix(
    list_id: Annotated[str, Path(pattern=r"^OL\d+L$")],
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict:
    return _process_list_delete(f"/lists/{list_id}")


async def lists_json():
    pass


async def list_view_json():
    pass


async def list_seeds():
    pass


async def list_editions_json():
    pass


async def list_subjects_json():
    pass
