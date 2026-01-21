from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from openlibrary.fastapi.services.subject_service import (
    BaseSubjectRequestParams,
    fetch_subject_data,
)

router = APIRouter()


@router.get("/publishers/{key:path}.json")
async def publisher_json(
    key: str,
    params: Annotated[BaseSubjectRequestParams, Depends()],
) -> dict[str, Any]:
    return await fetch_subject_data(
        key=key,
        params=params,
        path_prefix="/publishers",
        process_key_func=lambda k: k.replace("_", " "),
    )
