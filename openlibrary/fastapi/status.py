"""FastAPI router for server-status endpoints (testing environment, etc.).

The testing-environment endpoints expose the same data that powers the
/status deploy table on the legacy web.py page, so developers can query it
via JSON without a browser.

``/status/testing/stream`` serves the same snapshot as Server-Sent Events,
fed by ``cache.singleflight_cache``: one fleet-wide compute per
_SNAPSHOT_TTL_SECONDS, and every mutation invalidates it so every tab sees
the result within ~1s.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from openlibrary.core import cache
from openlibrary.core.env import get_ol_env
from openlibrary.fastapi.auth import AuthenticatedUser, require_maintainer
from openlibrary.plugins.openlibrary.status import (
    TestingStatus,
    add_prs,
    compute_testing_status,
    deploy_testing_status,
    pull_latest_prs,
    remove_testing_prs,
    restore_prs,
    set_prs_active,
)

logger = logging.getLogger("openlibrary.fastapi.status")

router = APIRouter(
    tags=["status"],
    dependencies=[Depends(require_maintainer)],
    include_in_schema=get_ol_env().LOCAL_DEV,
)

_STREAM_TICK_SECONDS = 1.0  # per-tab tick; normally a cache hit, no upstream I/O
_SNAPSHOT_TTL_SECONDS = 5.0  # fleet-wide: at most one upstream compute per window
_SNAPSHOT_KEY = "status.testing.snapshot"


async def _current_status() -> dict[str, Any] | None:
    """The panel snapshot, from the fleet-wide single-flight cache.

    None (no state file) is cacheable like any other value, so a stateless
    instance with N tabs makes zero Jenkins calls.
    """
    return await cache.singleflight_cache(_SNAPSHOT_KEY, compute_testing_status, ttl=_SNAPSHOT_TTL_SECONDS)


def _invalidate_cached_snapshot() -> None:
    """After a mutation: the next tick recomputes once, fleet-wide, and
    pushes the result to every stream within ~1s."""
    cache.invalidate(_SNAPSHOT_KEY)


class PRsRequest(BaseModel):
    prs: list[Annotated[int, Field(ge=1000)]] = Field(min_length=1)


class ActivePRsRequest(PRsRequest):
    active: bool


@router.get("/status/testing.json", response_model=TestingStatus)
async def testing_status() -> dict[str, Any]:
    """Return the testing environment status backing the /status deploy table."""
    result = await _current_status()
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No testing state file found")
    return result


async def _stream_events() -> AsyncIterator[ServerSentEvent]:
    """The stream body: the current snapshot first, then each change.

    Split from the endpoint so tests can bound the stream. Frames only
    changed payloads, so the event rate is the change rate; a failed tick
    is logged and skipped, so the stream itself never dies.
    """
    last_sent: dict[str, Any] | None = None
    while True:
        try:
            if (payload := await _current_status()) is not None and payload != last_sent:
                last_sent = payload
                yield ServerSentEvent(data=payload, event="status")
        except Exception:
            logger.warning("Status stream tick failed; retrying next tick", exc_info=True)
        await asyncio.sleep(_STREAM_TICK_SECONDS)


@router.get("/status/testing/stream", response_class=EventSourceResponse)
async def testing_status_stream() -> AsyncIterator[ServerSentEvent]:
    """Stream testing-environment snapshots as Server-Sent Events."""
    async for event in _stream_events():
        yield event


@router.post("/status/add")
async def add_prs_endpoint(user: Annotated[AuthenticatedUser, Depends(require_maintainer)], data: PRsRequest) -> dict[str, Any]:
    """Add PRs to the testing set."""
    result = await add_prs(data.prs, user.username)
    _invalidate_cached_snapshot()
    return result


@router.post("/status/remove")
def remove_prs(data: PRsRequest) -> dict[str, Any]:
    """Remove PRs from the testing environment state."""
    result = remove_testing_prs(data.prs)
    _invalidate_cached_snapshot()
    return result


@router.post("/status/restore")
def restore_status(data: PRsRequest) -> dict[str, bool]:
    """Restore PRs with staged removals."""
    result = restore_prs(data.prs)
    _invalidate_cached_snapshot()
    return result


@router.post("/status/pull-latest")
async def pull_latest(data: PRsRequest) -> dict[str, bool]:
    """Stage the latest GitHub commit for PRs in the testing set."""
    result = await pull_latest_prs(data.prs)
    _invalidate_cached_snapshot()
    return result


@router.patch("/status/testing/prs")
def set_prs_active_endpoint(data: ActivePRsRequest) -> dict[str, bool]:
    """Stage PRs to be enabled or disabled on the next testing deploy."""
    result = set_prs_active(data.prs, data.active)
    _invalidate_cached_snapshot()
    return result


@router.post("/status/refresh")
def refresh_status() -> dict[str, bool]:
    """Refresh testing-environment data from GitHub on the next read."""
    _invalidate_cached_snapshot()
    return {"ok": True}


@router.post("/status/deploy")
async def deploy_status() -> dict[str, bool | str]:
    """Deploy the staged testing-environment changes."""
    result = await deploy_testing_status()
    _invalidate_cached_snapshot()
    return result
