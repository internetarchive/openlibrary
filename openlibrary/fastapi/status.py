"""FastAPI router for server-status endpoints (testing environment, etc.).

The testing-environment endpoints expose the same data that powers the
/status deploy table on the legacy web.py page, so developers can query it
via JSON without a browser.
"""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from openlibrary.fastapi.auth import MaintainerDep  # noqa: TC001
from openlibrary.plugins.openlibrary.jenkins import jenkins_deploy_status
from openlibrary.plugins.openlibrary.status import (
    TestingState,
    TestingStatus,
    _evict_drift_cache,
    _get_pr_info_async,
    _load_testing_state,
    _parse_pr_numbers_from_string,
    _save_testing_state,
    add_prs_to_set_async,
    execute_deploy_async,
    load_testing_status_async,
    refresh_drift_cache,
    stage_pr_update,
)

SHOW_INTERNAL_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None
router = APIRouter(tags=["status"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@router.get(
    "/status/testing.json",
    response_model=TestingStatus,
    description="Returns the current status of the testing environment (PRs pinned for testing deploys).",
)
async def testing_status(_: MaintainerDep) -> TestingStatus:
    """Return the testing environment status backing the /status deploy table.

    The GitHub drift fetch and the Jenkins fetch run concurrently. The latest
    Jenkins run is ground truth for deploy state; the state file's time-window
    guess stands in only when Jenkins is down.
    """
    result, jenkins = await asyncio.gather(load_testing_status_async(), jenkins_deploy_status())
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No testing state file found")
    if jenkins:
        result = result.model_copy(
            update={
                "deploying": jenkins["status"] == "IN_PROGRESS",
                "deploy_started_at": jenkins["start_time"],
                "deploy_result": jenkins["status"],
                "deploy_finished_at": jenkins["end_time"],
                "deploy_stage": jenkins.get("current_stage", ""),
            }
        )
    return result


# ---------------------------------------------------------------------------
# Create — add PR(s) to the testing set
# ---------------------------------------------------------------------------


class AddPRsRequest(BaseModel):
    """Body for POST /status/prs.

    ``prs`` accepts a list of strings — PR numbers or full GitHub URLs,
    whitespace- or comma-separated (the server parses them the same way
    the legacy add box did).
    """

    prs: list[str] = Field(..., min_length=1, description="PR numbers or URLs to add")


@router.post(
    "/status/prs",
    description="Add one or more PRs to the testing set. Accepts PR numbers or GitHub URLs.",
)
async def add_prs(body: AddPRsRequest, _: MaintainerDep) -> dict:
    state = _load_testing_state() or TestingState(last_deploy_at="", prs=[])
    pr_numbers: list[int] = []
    for raw in body.prs:
        pr_numbers.extend(_parse_pr_numbers_from_string(raw))
    if not pr_numbers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid PR numbers provided")
    result = await add_prs_to_set_async(state, pr_numbers)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Update — stage a change on a single PR
# ---------------------------------------------------------------------------


class UpdatePRRequest(BaseModel):
    """Body for PATCH /status/prs/{id}.

    All fields are optional. Only the fields included in the request body
    are changed; omitted fields are left untouched.
    """

    active: bool | None = Field(None, description="Stage enable (true) or disable (false)")
    pull_latest: bool | None = Field(None, description="Stage fetch of latest HEAD commit")
    pending_removal: bool | None = Field(None, description="Stage (true) or unstage (false) removal")


@router.patch(
    "/status/prs/{pr_id}",
    description="Stage a change on a PR (enable, disable, pin, remove, or unstage removal).",
)
async def update_pr(pr_id: int, body: UpdatePRRequest, _: MaintainerDep) -> dict:
    state = _load_testing_state()
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No testing state found")

    target = next((p for p in state.prs if p.pr == pr_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"PR #{pr_id} not in testing set")

    changed = False

    # Stage enable/disable and/or removal (pure state mutation).
    if body.active is not None or body.pending_removal is not None:
        changed = stage_pr_update(state, [pr_id], active=body.active, pending_removal=body.pending_removal)

    # Stage pull-latest (fetch current HEAD from GitHub).
    if body.pull_latest is True:
        info = await _get_pr_info_async(pr_id)
        if info.get("head_sha") and not info.get("error"):
            target.pull_latest_sha = info["head_sha"]
            changed = True

    if changed:
        _save_testing_state(state)
        _evict_drift_cache()

    return {"ok": True}


# ---------------------------------------------------------------------------
# Deploy — trigger Jenkins and flush all pending changes
# ---------------------------------------------------------------------------


@router.post(
    "/status/deploy",
    description="Trigger a Jenkins deploy, flushing all pending changes (pins, toggles, removals).",
)
async def deploy_prs(_: MaintainerDep) -> dict:
    state = _load_testing_state()
    if not state:
        return {"ok": True}
    result = await execute_deploy_async(state)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Refresh — evict the drift cache
# ---------------------------------------------------------------------------


@router.post(
    "/status/refresh",
    description="Evict the GitHub drift cache so the next status fetch is fresh.",
)
async def refresh_status(_: MaintainerDep) -> dict:
    refresh_drift_cache()
    return {"ok": True}
