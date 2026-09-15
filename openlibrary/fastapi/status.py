"""FastAPI router for server-status endpoints (testing environment, etc.).

The testing-environment endpoints expose the same data that powers the
/status deploy table on the legacy web.py page, so developers can query it
via JSON without a browser.
"""

from __future__ import annotations

import asyncio
import os
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, status
from pydantic import BeforeValidator

from openlibrary.fastapi.auth import MaintainerDep  # noqa: TC001
from openlibrary.plugins.openlibrary.jenkins import jenkins_deploy_status
from openlibrary.plugins.openlibrary.status import (
    TestingStatus,
    add_prs,
    load_testing_status_async,
    parse_pr_numbers,
)

SHOW_INTERNAL_IN_SCHEMA = os.getenv("LOCAL_DEV") is not None
router = APIRouter(tags=["status"], include_in_schema=SHOW_INTERNAL_IN_SCHEMA)


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


# The add form posts a single ``pr`` field holding whitespace/comma-separated
# numbers or PR URLs; the service-layer tokenizer turns it into ints.
PrNumbersDep = Annotated[list[int], BeforeValidator(parse_pr_numbers), Form(alias="pr")]


@router.post("/status/add")
async def add_prs_endpoint(
    user: MaintainerDep,
    pr_numbers: PrNumbersDep = [],  # noqa: B006
) -> dict[str, Any]:
    """Add PRs to the testing set."""
    if not pr_numbers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid PR numbers specified",
        )
    return await add_prs(pr_numbers, user.username)
