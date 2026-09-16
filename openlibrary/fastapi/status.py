"""FastAPI router for server-status endpoints (testing environment, etc.).

The testing-environment endpoints expose the same data that powers the
/status deploy table on the legacy web.py page, so developers can query it
via JSON without a browser.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from openlibrary.core.env import get_ol_env
from openlibrary.fastapi.auth import AuthenticatedUser, require_maintainer
from openlibrary.plugins.openlibrary.jenkins import jenkins_deploy_status
from openlibrary.plugins.openlibrary.status import (
    TestingStatus,
    add_prs,
    deploy_testing_status,
    load_testing_status_async,
    pull_latest_prs,
    refresh_testing_status,
    remove_testing_prs,
    restore_prs,
    set_prs_active,
)

router = APIRouter(
    tags=["status"],
    dependencies=[Depends(require_maintainer)],
    include_in_schema=get_ol_env().LOCAL_DEV,
)


class PRsRequest(BaseModel):
    prs: list[Annotated[int, Field(ge=1000)]] = Field(min_length=1)


class ActivePRsRequest(PRsRequest):
    active: bool


@router.get("/status/testing.json", response_model=TestingStatus)
async def testing_status() -> TestingStatus:
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


@router.post("/status/add")
async def add_prs_endpoint(user: Annotated[AuthenticatedUser, Depends(require_maintainer)], data: PRsRequest) -> dict[str, Any]:
    """Add PRs to the testing set."""
    return await add_prs(data.prs, user.username)


@router.post("/status/remove")
def remove_prs(data: PRsRequest) -> dict[str, Any]:
    """Remove PRs from the testing environment state."""
    return remove_testing_prs(data.prs)


@router.post("/status/restore")
def restore_status(data: PRsRequest) -> dict[str, bool]:
    """Restore PRs with staged removals."""
    return restore_prs(data.prs)


@router.post("/status/pull-latest")
async def pull_latest(data: PRsRequest) -> dict[str, bool]:
    """Stage the latest GitHub commit for PRs in the testing set."""
    return await pull_latest_prs(data.prs)


@router.patch("/status/testing/prs")
def set_prs_active_endpoint(data: ActivePRsRequest) -> dict[str, bool]:
    """Stage PRs to be enabled or disabled on the next testing deploy."""
    return set_prs_active(data.prs, data.active)


@router.post("/status/refresh")
def refresh_status() -> dict[str, bool]:
    """Refresh testing-environment data from GitHub on the next read."""
    return refresh_testing_status()


@router.post("/status/deploy")
def deploy_status() -> dict[str, bool | str]:
    """Deploy the staged testing-environment changes."""
    return deploy_testing_status()
