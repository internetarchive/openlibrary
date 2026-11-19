from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel

from openlibrary.fastapi.services.subject_service import (
    BaseSubjectRequestParams,
    fetch_subject_data,
)
from openlibrary.plugins.worksearch.publishers import suggest_publishers

router = APIRouter()


class PublisherSuggestion(BaseModel):
    value: str
    count: int


# Declared before the {key} route, which would otherwise take "_autocomplete" for a publisher.
# Plain def: memcache and the Solr bridge are blocking, so it runs in the threadpool.
@router.get("/publishers/_autocomplete")
def publishers_autocomplete(
    q: Annotated[str, Query(max_length=100, description="What has been typed so far.")] = "",
    limit: Annotated[int, Query(gt=0, le=20)] = 8,
) -> list[PublisherSuggestion]:
    """Publisher names already in the catalog that match a half-typed name, with how many works carry each."""
    return [PublisherSuggestion(**row) for row in suggest_publishers(q, limit)]


@router.get("/publishers/{key:path}.json")
async def publisher_json(
    key: Annotated[str, Path()],
    params: Annotated[BaseSubjectRequestParams, Depends()],
) -> dict[str, Any]:
    # Replace underscores with spaces in the key
    processed_key = key.replace("_", " ")
    return await fetch_subject_data(
        key=processed_key,
        params=params,
        path_prefix="/publishers",
    )
