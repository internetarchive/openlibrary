"""FastAPI router for server-status endpoints (testing environment, etc.).

The testing-environment endpoints expose the same data that powers the
/status deploy table on the legacy web.py page, so developers can query it
via JSON without a browser.
"""

from __future__ import annotations

import asyncio
import os
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from openlibrary.fastapi.auth import MaintainerDep  # noqa: TC001
from openlibrary.plugins.openlibrary.jenkins import jenkins_deploy_status
from openlibrary.plugins.openlibrary.status import (
    TestingStatus,
    add_prs,
    deploy_testing_status,
    load_testing_status_async,
    pull_latest_prs,
    refresh_testing_status,
    remove_testing_prs,
    set_prs_active,
)

SHOW_INTERNAL_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None
router = APIRouter(tags=["status"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)


class PRsRequest(BaseModel):
    prs: list[Annotated[int, Field(ge=1000)]] = Field(min_length=1)


class ActivePRsRequest(PRsRequest):
    active: bool


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


@router.post("/status/add")
async def add_prs_endpoint(
    user: MaintainerDep,
    data: PRsRequest,
) -> dict[str, Any]:
    """Add PRs to the testing set."""
    return await add_prs(data.prs, user.username)


@router.post("/status/remove")
def remove_prs(
    _: MaintainerDep,
    data: PRsRequest,
) -> dict[str, Any]:
    """Remove PRs from the testing environment state."""
    return remove_testing_prs(data.prs)


@router.post("/status/pull-latest")
async def pull_latest(
    _: MaintainerDep,
    data: PRsRequest,
) -> dict[str, bool]:
    """Stage the latest GitHub commit for PRs in the testing set."""
    return await pull_latest_prs(data.prs)


@router.patch("/status/testing/prs")
def set_prs_active_endpoint(
    _: MaintainerDep,
    data: ActivePRsRequest,
) -> dict[str, Any]:
    """Stage PRs to be enabled or disabled on the next testing deploy."""
    return set_prs_active(data.prs, data.active)


@router.post("/status/refresh")
def refresh_status(_: MaintainerDep) -> dict[str, bool]:
    """Refresh testing-environment data from GitHub on the next read."""
    return refresh_testing_status()


@router.post("/status/deploy")
def deploy_status(_: MaintainerDep) -> dict[str, bool | str]:
    """Deploy the staged testing-environment changes."""
    return deploy_testing_status()
