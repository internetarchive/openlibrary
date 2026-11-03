"""What the /tasks pages fetch after load: the "happening now" feed and the dashboard's list, both polled by contribute.js."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from openlibrary.contribute import feed
from openlibrary.core.jinja import render_jinja_template
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.plugins.openlibrary import contribute

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
    rows: list[FeedRow]


# Plain def: the memcache read is blocking I/O, so it runs in the threadpool rather than on the event loop.
@router.get("/tasks/feed.json", response_model=FeedResponse)
def tasks_feed(
    limit: Annotated[int, Query(gt=0, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, description="Where in the rotation to start.")] = 0,
) -> FeedResponse:
    """Recent human edits to catalog records as rows for the Tasks page feed, rotated and restamped back from now."""
    rows = feed.recent_rows(limit, offset)
    return FeedResponse(rows=[FeedRow(**r) for r in rows])


# Plain def: the memcache read and the edition loads are blocking I/O, so they run in the threadpool.
@router.get("/tasks/rows", response_class=HTMLResponse, include_in_schema=False)
def tasks_rows(
    _user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    task: Annotated[str, Query(description="The dashboard filter; unknown values mean all tasks.")] = "",
) -> Response:
    """The dashboard's list on its own, for a page that rendered placeholders: 202 while the pool is still being built."""
    if (rows := contribute.build_task_rows(contribute.normalize_filter(task))) is None:
        return Response(status_code=202)
    return HTMLResponse(render_jinja_template("contribute/rows.html.jinja", rows=rows))
