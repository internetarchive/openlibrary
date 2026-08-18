"""FastAPI router for server-status endpoints (testing environment, etc.).

The testing-environment endpoints expose the same data that powers the
/status deploy table on the legacy web.py page, so developers can query it
via JSON without a browser.
"""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from openlibrary.fastapi.auth import MaintainerDep  # noqa: TC001
from openlibrary.plugins.openlibrary.status import jenkins_deploy_status, load_testing_status_async

SHOW_INTERNAL_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None
router = APIRouter(tags=["status"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)


class TestingPRResponse(BaseModel):
    """A single PR in the testing environment, with live drift info merged in. Mirrors TestingPRStatus."""

    model_config = ConfigDict(from_attributes=True)

    pr: int = Field(..., description="GitHub pull request number")
    title: str = Field(..., description="PR title")
    commit: str = Field(..., description="Pinned commit SHA (full)")
    active: bool = Field(..., description="Whether the PR is active in the testing set")
    added_at: str = Field(..., description="ISO timestamp when the PR was added")
    added_by: str = Field(..., description="OL username that added the PR")
    pull_latest_sha: str = Field(..., description="Pending SHA from 'Fetch Latest'; applied on deploy. Empty if none")
    pending_active: bool | None = Field(..., description="Pending enable/disable; applied on deploy. Null if none")
    author: str = Field(..., description="GitHub login of the PR author")
    author_avatar: str = Field(..., description="GitHub avatar URL of the PR author")
    assignee: str = Field(..., description="GitHub login of the assignee, empty if unassigned")
    assignee_avatar: str = Field(..., description="GitHub avatar URL of the assignee")
    head_sha: str = Field(..., description="Current branch HEAD (short SHA); empty if GitHub unavailable")
    drift: int = Field(..., description="Commits the pinned commit is behind HEAD; -1 if unknown")
    merged: bool = Field(..., description="Whether the PR has been merged into master")
    is_new: bool = Field(..., description="Whether the PR was added since the last deploy")
    live_now: bool = Field(..., description="Whether the last deploy put this PR on the box (it is running now)")
    merge_conflict: bool = Field(..., description="Whether the last deploy's merge of this PR conflicted, so it did not land")
    action: str = Field(..., description="What the next deploy does with this PR: add, pin, enable, disable, remove, or empty when unchanged")
    in_set: bool = Field(..., description="Whether the PR is still in the testing set; False for rows dropped from the set but still on the box")


class PendingChangeResponse(BaseModel):
    """One staged change that the next deploy would apply."""

    pr: int = Field(..., description="GitHub pull request number")
    title: str = Field(..., description="PR title")
    kind: str = Field(..., description="One of: add, pin, enable, disable, remove")
    detail: str = Field("", description="Short SHA for add/pin changes; empty otherwise")
    reason: str = Field("", description="Why a removal is staged: merged or dropped; empty otherwise")


class TestingStatusResponse(BaseModel):
    """Status of the testing environment (the /status deploy table). Mirrors TestingStatus."""

    model_config = ConfigDict(from_attributes=True)

    last_deploy_at: str = Field(..., description="ISO timestamp of the last deploy; empty if never deployed")
    deploy_started_at: str = Field(..., description="ISO timestamp of the last deploy Jenkins accepted; empty if never")
    deploying: bool = Field(..., description="Whether a build is still running: the latest Jenkins run when reachable, else a time-window guess")
    deploy_result: str = Field("", description="Latest ol-dev1-deploy run status; empty when Jenkins is unreachable")
    deploy_finished_at: str = Field("", description="ISO end time of the latest Jenkins run; empty if running or unreachable")
    has_pending: bool = Field(..., description="Whether there are pending changes ready to deploy")
    pending_changes: list[PendingChangeResponse] = Field(default_factory=list, description="What the next deploy would apply")
    prs: list[TestingPRResponse] = Field(..., description="PRs in the testing set")


@router.get(
    "/status/testing.json",
    response_model=TestingStatusResponse,
    description="Returns the current status of the testing environment (PRs pinned for testing deploys).",
)
async def testing_status(_: MaintainerDep) -> TestingStatusResponse:
    """Return the testing environment status backing the /status deploy table.

    The GitHub drift fetch and the Jenkins fetch run concurrently; on a cold
    cache the two round-trips overlap instead of stacking.
    """
    result, jenkins = await asyncio.gather(load_testing_status_async(), jenkins_deploy_status())
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No testing state file found")
    response = TestingStatusResponse.model_validate(result)
    if jenkins:
        # The latest Jenkins run is ground truth; the state file only knows the
        # trigger, so its time-window guess stands in only when Jenkins is down.
        response.deploying = jenkins["status"] == "IN_PROGRESS"
        response.deploy_result = jenkins["status"]
        response.deploy_finished_at = jenkins["end_time"]
    return response
