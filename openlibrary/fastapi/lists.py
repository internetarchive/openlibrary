from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path
from fastapi.responses import Response

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


async def list_subjects_json():
    pass
