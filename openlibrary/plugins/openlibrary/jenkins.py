"""Client for Open Library's Jenkins deploy pipeline.

The status panel only ever learns that a build was *triggered* (Jenkins never
calls back), so the pipeline's own run list is the ground truth for whether a
build is still running and how it ended. These functions read that run list
(``jenkins_deploy_status``) and kick off rebuilds (``trigger_rebuild``).
"""

from __future__ import annotations

import datetime
import http.client
import urllib.request
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import httpx

from infogami import config

if TYPE_CHECKING:
    from openlibrary.plugins.openlibrary.status import TestingPR

JENKINS_URL = "https://jenkins.openlibrary.org/job/testing-deploy/buildWithParameters"
JENKINS_JOB_URL = "https://jenkins.openlibrary.org/job/ol-dev1-deploy%20(internal)/"
# The deploy pipeline's own run list (newest first). fullStages=true brings the
# per-stage status so the panel can name the stage a running build is on.
JENKINS_RUNS_URL = "https://jenkins.openlibrary.org/job/ol-dev1-deploy%20(internal)/wfapi/runs?fullStages=true"


async def jenkins_deploy_status() -> dict | None:
    """Return the latest ol-dev1-deploy run: {status, start_time, end_time, current_stage}.

    ``status`` is Jenkins' own verdict — IN_PROGRESS, SUCCESS, FAILURE,
    ABORTED, … — so the panel can say a deploy finished instead of guessing
    from a time window. ``current_stage`` names the stage a running build is
    on (empty when not running). None when Jenkins is unreachable or reports
    nothing.

    Async: this runs inside the FastAPI event loop (see fastapi/status.py), so
    it uses httpx rather than blocking urllib. Not cached: the panel polls
    every few seconds, and wfapi is cheap — a cached answer would already be
    stale when shown.
    """
    result = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(JENKINS_RUNS_URL, headers={"User-Agent": "openlibrary-status"})
            runs = resp.json()
        if isinstance(runs, list) and runs and isinstance(runs[0], dict):
            run = runs[0]
            result = {
                "status": run.get("status", ""),
                "start_time": _epoch_ms_to_iso(run.get("startTimeMillis")),
                "end_time": _epoch_ms_to_iso(run.get("endTimeMillis")),
                "current_stage": _current_stage(run),
            }
    except httpx.HTTPError, ValueError:
        # HTTPError covers network failures and non-2xx; ValueError covers a
        # non-JSON body (json.JSONDecodeError is a ValueError subclass).
        result = None
    return result


def _epoch_ms_to_iso(epoch_ms) -> str:
    """Jenkins timestamps are epoch milliseconds; the panel reads ISO strings."""
    if not epoch_ms:
        return ""
    return datetime.datetime.fromtimestamp(epoch_ms / 1000, tz=datetime.UTC).isoformat()


def _current_stage(run: dict) -> str:
    """Name of the stage a running build is on; empty when not running.

    wfapi stage entries carry their own status, so the in-progress stage is
    the one Jenkins is executing right now.
    """
    if run.get("status") != "IN_PROGRESS":
        return ""
    for stage in run.get("stages") or []:
        if stage.get("status") == "IN_PROGRESS":
            return stage.get("name", "")
    return ""


def trigger_rebuild(prs: list[TestingPR]) -> str:
    """Trigger the testing-deploy job for ``prs`` (each with ``pr``/``title``/``active``).

    Returns ``"triggered"``, ``"failed"`` (Jenkins unreachable or refused), or
    ``"unconfigured"`` when there is no jenkins_token, as in local dev.
    """
    token = getattr(config, "jenkins_token", None)
    if not token:
        return "unconfigured"
    lines = "\n".join(f"origin pull/{p.pr}/head  # {p.title}" for p in prs if p.active)
    url = f"{JENKINS_URL}?{urlencode({'token': token, 'GH_REPO_AND_BRANCH': lines})}"
    try:
        urllib.request.urlopen(url, timeout=10)
        return "triggered"
    except OSError, http.client.HTTPException, ValueError:
        # OSError covers URLError/HTTPError plus the read-timeout and dropped-
        # connection errors that escape urlopen unwrapped.
        return "failed"
