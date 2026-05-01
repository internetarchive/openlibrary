from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from infogami.infobase import client
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.plugins.openlibrary.lists import lists_delete as _LegacyListsDelete
from openlibrary.utils.request_context import site

router = APIRouter()


@router.post(
    "/people/{username}/lists/{list_id}/delete.json",
    description="Delete a list owned by the given user.",
)
def lists_delete(
    username: str,
    list_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict:
    key = f"/people/{username}/lists/{list_id}"

    if username != user.username:
        raise HTTPException(status_code=403, detail="Permission denied.")

    doc = site.get().get(key)
    if doc is None or doc.type.key != "/type/list":
        raise HTTPException(status_code=404, detail="Not found.")

    try:
        _LegacyListsDelete.process_delete(doc, key)
    except client.ClientException as e:
        raise HTTPException(status_code=int(e.status.split()[0]), detail=str(e))

    return {"status": "ok"}


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
