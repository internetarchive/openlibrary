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
    # Replace underscores with spaces in the key
    processed_key = key.replace("_", " ")
    return await fetch_subject_data(
        key=processed_key,
        params=params,
        path_prefix="/publishers",
    )
