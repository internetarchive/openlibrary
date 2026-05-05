from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import Response

from openlibrary.plugins.openlibrary.lists import get_list_subjects

router = APIRouter()


async def lists_delete(filename: Annotated[str, Path()]) -> Response:
    return Response(status_code=200)


async def lists_json():
    pass


async def list_view_json():
    pass


async def list_seeds():
    pass


async def list_editions_json():
    pass


@router.get("/people/{username}/lists/{list_id}/subjects.json")
def list_subjects_json_user(username: str, list_id: str, limit: int = 20) -> dict:
    key = f"/people/{username}/lists/{list_id}"
    if data := get_list_subjects(key, limit):
        return data
    raise HTTPException(status_code=404, detail="List not found")


@router.get("/lists/{list_id}/subjects.json")
def list_subjects_json_public(list_id: str, limit: int = 20) -> dict:
    key = f"/lists/{list_id}"
    if data := get_list_subjects(key, limit):
        return data
    raise HTTPException(status_code=404, detail="List not found")


@router.get("/series/{list_id}/subjects.json")
def list_subjects_json_series(list_id: str, limit: int = 20) -> dict:
    key = f"/series/{list_id}"
    if data := get_list_subjects(key, limit):
        return data
    raise HTTPException(status_code=404, detail="List not found")
