"""The /tasks page's "happening now" feed, polled by openlibrary/plugins/openlibrary/js/contribute.js."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from openlibrary.contribute import feed
from openlibrary.utils.request_context import site

router = APIRouter()


class FeedRow(BaseModel):
    id: str
    key: str
    title: str
    authors: str
    cover_url: str
    kind: str
    action: str
    editor: str
    editor_key: str
    comment: str
    timestamp: str


class FeedResponse(BaseModel):
    mode: Literal["recent", "static"]
    rows: list[FeedRow]


@router.get("/tasks/feed.json", response_model=FeedResponse)
async def tasks_feed(
    mode: Annotated[Literal["recent", "static"], Query(description="recent reads the pool of real recent edits; static the fixture.")] = "recent",
    limit: Annotated[int, Query(gt=0, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, description="Where in the rotation to start.")] = 0,
) -> FeedResponse:
    """Recent human edits to catalog records as rows for the Tasks page feed, rotated and restamped back from now."""
    rows = feed.sample_rows(limit, offset) if mode == "static" else feed.recent_rows(site.get(), limit, offset)
    return FeedResponse(mode=mode, rows=[FeedRow(**r) for r in rows])
