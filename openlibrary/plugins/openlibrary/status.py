import asyncio
import contextlib
import datetime
import json
import re
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import web
from pydantic import BaseModel, Field, field_serializer

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import public, render_template
from openlibrary.accounts import get_current_user
from openlibrary.core import cache, stats
from openlibrary.core.env import get_ol_env
from openlibrary.plugins.openlibrary.jenkins import JENKINS_JOB_URL, trigger_rebuild
from openlibrary.utils import get_software_version
from openlibrary.utils.async_utils import async_bridge, cache_per_event_loop

status_info: dict[str, Any] = {}

TESTING_STATE_FILE = Path("./_testing-prs.json")
_GITHUB_API_BASE = "https://api.github.com/repos/internetarchive/openlibrary"
_DRIFT_CACHE_KEY = "status.github_pr_drift"
_DRIFT_CACHE_TTL = 60  # 1 minute
# Jenkins never calls back, so a triggered deploy is only ever presumed to be
# running. After this long we stop claiming it is, without claiming it worked.
_DEPLOY_WINDOW = 10 * 60  # 10 minutes
# Reading order for the pending-change plan: additions first, removals last.
_CHANGE_ORDER = {"add": 0, "pin": 1, "enable": 2, "disable": 3, "remove": 4}


class GitHubAPIError(Exception):
    """A GitHub lookup failed. Base for the failure modes callers act on."""


class PRNotFoundError(GitHubAPIError):
    """GitHub answered 404: the PR number doesn't exist, or isn't visible."""


class GitHubUnavailableError(GitHubAPIError):
    """Rate limits, network outages, timeouts, or an unparsable response."""


class status(delegate.page):
    def GET(self):
        is_maintainer_user = _is_maintainer()
        has_testing_state = _load_testing_state() is not None
        show_testing = has_testing_state and is_maintainer_user
        return render_template(
            "status",
            status_info,
            features_table=get_features_table(),
            dev_merged_status=get_dev_merged_status(),
            is_maintainer=is_maintainer_user,
            has_testing_state=has_testing_state,
            show_testing=show_testing,
            jenkins_job_url=JENKINS_JOB_URL,
        )


def _json_ok() -> delegate.RawText:
    """JSON success response for the status action endpoints."""
    return delegate.RawText(json.dumps({"ok": True}), content_type="application/json")


def _json_error(error: str) -> delegate.RawText:
    """JSON failure response: {"ok": false, "error": "<code>"}.

    Business outcomes (an add GitHub couldn't verify, a deploy Jenkins
    refused) answer 200 with ok=false so the panel can show a specific
    message; auth and input errors stay real HTTP errors (401/400).
    """
    return delegate.RawText(json.dumps({"ok": False, "error": error}), content_type="application/json")


def remove_testing_prs(prs: list[int]) -> dict[str, Any]:
    """Remove PRs from the testing state."""
    to_remove = {int(p) for p in prs}
    state = _load_testing_state()
    if not state or not to_remove:
        return {"ok": True, "staged_prs": [], "removed_prs": []}
    staged_prs = []
    removed_prs = []
    kept = []
    for p in state.prs:
        if p.pr in to_remove:
            if not _live_now(state, p):
                removed_prs.append(p.pr)
                continue
            p.pending_remove = True
            staged_prs.append(p.pr)
        kept.append(p)
    state.prs = kept
    _save_testing_state(state)
    return {"ok": True, "staged_prs": staged_prs, "removed_prs": removed_prs}


class status_restore(delegate.page):
    path = "/status/restore"

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        i = web.input(prs=[])
        to_restore = {int(p) for p in i.prs}
        state = _load_testing_state()
        if not state or not to_restore:
            return _json_ok()
        for p in state.prs:
            if p.pr in to_restore:
                p.pending_remove = False
        _save_testing_state(state)
        return _json_ok()


def set_prs_active(prs: list[int], active: bool) -> dict[str, bool]:
    """Stage an active-state change for PRs in the testing set."""
    state = _load_testing_state()
    if not state:
        return {"ok": True}
    requested = set(prs)
    for p in state.prs:
        if p.pr in requested:
            p.pending_active = active
    _save_testing_state(state)
    return {"ok": True}


class status_pull_latest(delegate.page):
    path = "/status/pull-latest"

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        i = web.input(prs=[])
        to_update = {int(p) for p in i.prs}
        state = _load_testing_state()
        if not state or not to_update:
            return _json_ok()
        for p in state.prs:
            if p.pr in to_update:
                try:
                    info = _get_pr_info(p.pr)
                except GitHubAPIError:
                    # GitHub is down or the PR is gone. This endpoint has always
                    # treated that as "nothing to update" and answered ok, so the
                    # row is left alone rather than failing the whole request.
                    continue
                if info.head_sha and info.head_sha != p.commit:
                    p.pull_latest_sha = info.head_sha
        _save_testing_state(state)
        return _json_ok()


class status_deploy(delegate.page):
    path = "/status/deploy"

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        state = _load_testing_state()
        if not state:
            return _json_ok()
        # Drop staged removals and merged/closed PRs on the *un-mutated* state;
        # persist=False so the drift metadata refresh can never write staged
        # changes before Jenkins accepts the build.
        drift_info, _ = _get_drift_info(state, persist=False)
        state.prs = [p for p in state.prs if not p.pending_remove and not _drop_reason(drift_info.get(p.pr, {}))]
        # Apply all pending changes before deploying
        for p in state.prs:
            if p.pull_latest_sha:
                p.commit = p.pull_latest_sha
                p.pull_latest_sha = ""
            if p.pending_active is not None:
                p.active = p.pending_active
                p.pending_active = None
        # Nothing above is persisted until Jenkins accepts the build, so a failed
        # trigger leaves every staged change intact and retryable.
        outcome = trigger_rebuild(state.prs)
        if outcome == "failed":
            return _json_error("deploy_failed")
        user = get_current_user()
        state.last_deploy_at = datetime.datetime.now(datetime.UTC).isoformat()
        state.deployed_by = user.key.split("/")[-1] if user else ""
        # What this build puts on the box: active PRs only, the same filter
        # trigger_rebuild sends. Recorded so a later removal has a set to be
        # missing from — nothing else survives one.
        state.deployed = {p.pr: p.title for p in state.prs if p.active}
        if outcome == "triggered":
            state.deploy_started_at = state.last_deploy_at
        _save_testing_state(state)
        _evict_drift_cache()
        # "unconfigured" (no Jenkins token, local dev) still advances state so
        # the panel is exercisable, but the response says the box was never
        # touched so the UI doesn't claim a real deploy happened.
        if outcome == "triggered":
            return _json_ok()
        return _json_error("deploy_unconfigured")


class status_refresh(delegate.page):
    path = "/status/refresh"

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        _evict_drift_cache()
        return _json_ok()


def _is_deploying(state: TestingState) -> bool:
    """Whether a Jenkins build is presumed to still be running.

    Jenkins gives us no completion signal, so this is a time window, not an
    observation: it says a build was started recently, never that it worked.
    """
    if not state.deploy_started_at:
        return False
    with contextlib.suppress(ValueError):
        started = datetime.datetime.fromisoformat(state.deploy_started_at)
        if started.tzinfo is None:
            started = started.replace(tzinfo=datetime.UTC)
        return (datetime.datetime.now(datetime.UTC) - started).total_seconds() < _DEPLOY_WINDOW
    return False


def _live_now(state: TestingState, p: TestingPR) -> bool:
    """Whether the last deploy put this PR on the box.

    A populated ``deployed`` record is authoritative. The record postdates most
    state files, so an empty one means "pre-record" rather than "nothing was
    ever deployed": anything added before the last deploy was part of it.
    """
    if state.deployed:
        return p.pr in state.deployed
    return bool(state.last_deploy_at and p.added_at <= state.last_deploy_at)


def _drop_reason(info: dict) -> str:
    """Why the deploy drops a PR — ``merged`` or ``closed`` — or "" to keep it.

    The deploy filter and the pending-change plan both consume this, so the
    plan can never promise a drop the deploy doesn't perform, or vice versa.
    """
    if info.get("merged", False):
        return "merged"
    if info.get("closed", False):
        return "closed"
    return ""


def _pending_changes(state: TestingState, drift_info: dict) -> list[PendingChange]:
    """The plan: what deploying would change, one entry per staged change.

    Every row action writes staged intent that only status_deploy applies, so
    this walks the same fields it flushes. A PR merged to master — or closed
    without merging — is dropped on deploy regardless of what else is staged on
    it, so it yields one ``remove`` and nothing more.

    Removal is staged like everything else: ``pending_remove`` marks the row
    and the deploy deletes it. Rows removed outright by code that predates the
    flag survive only in ``state.deployed``; those are recovered at the end by
    diffing it — what the last deploy built — against what is left.
    """
    last_deploy = state.last_deploy_at
    changes: list[PendingChange] = []
    for p in state.prs:
        if reason := _drop_reason(drift_info.get(p.pr, {})):
            changes.append(PendingChange(pr=p.pr, title=p.title, kind="remove", reason=reason, detail=""))
            continue
        if p.pending_remove:
            # A staged removal drops the row on deploy, so nothing else staged
            # on it matters. No reason: this one the maintainer asked for.
            changes.append(PendingChange(pr=p.pr, title=p.title, kind="remove", detail=""))
            continue
        if not last_deploy or p.added_at > last_deploy:
            # A pin staged on a PR that isn't live yet isn't a separate change:
            # it's just the SHA the PR lands at, so report the effective one.
            changes.append(PendingChange(pr=p.pr, title=p.title, kind="add", detail=p.short_pull_latest or p.short_commit))
        elif p.pull_latest_sha:
            changes.append(PendingChange(pr=p.pr, title=p.title, kind="pin", detail=p.short_pull_latest))
        if (toggle := p.pending_toggle) is not None:
            changes.append(PendingChange(pr=p.pr, title=p.title, kind="enable" if toggle else "disable", detail=""))
    # Deployed but no longer in the set: removed outright by pre-`pending_remove`
    # code, and still on the box until the next deploy drops it. State files
    # written before `deployed` existed start empty here, so their first deploy
    # is what makes removals visible.
    # ``reason`` separates these from the merged ones above, which are the same
    # kind for a different cause and must not borrow each other's wording.
    remaining = {p.pr for p in state.prs}
    for pr, title in state.deployed.items():
        if pr not in remaining:
            changes.append(PendingChange(pr=pr, title=title, kind="remove", reason="dropped", detail=""))
    changes.sort(key=lambda c: (_CHANGE_ORDER[c.kind], c.pr))
    return changes


def get_dev_merged_status():
    return DevMergedStatus.from_file()


@dataclass
class DevMergedStatus:
    git_status: str
    pr_statuses: list[PRStatus]
    footer: str

    @staticmethod
    def from_output(output: str) -> DevMergedStatus:
        dev_merged_pieces = output.split("\n---\n")
        return DevMergedStatus(
            git_status=dev_merged_pieces[0],
            pr_statuses=list(map(PRStatus.from_output, dev_merged_pieces[1:-1])),
            footer=dev_merged_pieces[-1],
        )

    @staticmethod
    def from_file() -> DevMergedStatus | None:
        """If we're on testing and the file exists, return staged PRs"""
        fp = Path("./_dev-merged_status.txt")
        if fp.exists() and (contents := fp.read_text()):
            return DevMergedStatus.from_output(contents)
        return None

    def get_github_search_link(self) -> str:
        """Constructs a GitHub search URL for all PRs in pr_statuses."""

        pull_ids = [pr.pull_id for pr in self.pr_statuses if pr.pull_id]

        return f"https://github.com/internetarchive/openlibrary/pulls?{urlencode({'q': 'is:pr is:open ' + ' '.join([f'#{num}' for num in pull_ids])})}"


@dataclass
class PRStatus:
    pull_line: str
    status: str
    body: str

    @property
    def name(self) -> str | None:
        if "#" in self.pull_line:
            return self.pull_line.split(" # ")[1]
        else:
            return self.pull_line

    @property
    def pull_id(self) -> int | None:
        if m := re.match(r"^origin pull/(\d+)", self.pull_line):
            return int(m.group(1))
        else:
            return None

    @property
    def link(self) -> str | None:
        if self.pull_id is not None:
            return f"https://github.com/internetarchive/openlibrary/pull/{self.pull_id}"
        else:
            return None

    @staticmethod
    def from_output(output: str) -> PRStatus:
        lines = output.strip().split("\n")
        return PRStatus(pull_line=lines[0], status=lines[-1], body="\n".join(lines[1:]))


class GitHubPRInfo(BaseModel):
    """The PR metadata fetched from GitHub.

    A transport shape, not persisted state: it carries only what GitHub
    reports, so a value here is always real data (``_get_pr_info_async`` raises
    rather than returning placeholders).
    """

    pr: int
    title: str
    head_sha: str
    author: str = ""
    author_avatar: str = ""
    assignee: str = ""
    assignee_avatar: str = ""


class TestingPR(BaseModel):
    pr: int
    commit: str  # pinned commit SHA (full)
    # The defaults mirror the legacy from_dict, so state files written before
    # these fields existed still load.
    active: bool = True
    title: str = ""
    added_at: str = ""  # ISO timestamp
    added_by: str = ""  # OL username
    pull_latest_sha: str = ""  # pending SHA from "Fetch Latest"; applied on deploy
    pending_active: bool | None = None  # pending enable/disable; applied on deploy
    pending_remove: bool = False  # staged removal; the deploy deletes the row
    author: str = ""  # GitHub login of PR author
    author_avatar: str = ""  # GitHub avatar URL (append &s=N for sizing)
    assignee: str = ""  # GitHub login of assignee, empty if unassigned
    assignee_avatar: str = ""  # GitHub avatar URL for assignee

    @field_serializer("pending_active")
    def _serialize_pending_active(self, value: bool | None) -> bool | None:
        # The state file and the API both normalize: a toggle staged back to
        # the live state changes nothing on deploy, so it isn't persisted or
        # served. ``pending_toggle`` is the effective staged direction.
        return self.pending_toggle

    @classmethod
    def from_github(cls, info: GitHubPRInfo, username: str) -> TestingPR:
        """Build a newly added row from GitHub metadata, credited to ``username``.

        ``added_at`` is set explicitly rather than defaulted: the field defaults
        to "" so state files predating it still load, and a factory default
        would stamp an invented "now" onto legacy rows — making them look newly
        added and rewriting their real timestamps on the next save.
        """
        return cls(
            pr=info.pr,
            commit=info.head_sha,
            title=info.title,
            added_at=datetime.datetime.now(datetime.UTC).isoformat(),
            added_by=username,
            author=info.author,
            author_avatar=info.author_avatar,
            assignee=info.assignee,
            assignee_avatar=info.assignee_avatar,
        )

    @property
    def short_commit(self) -> str:
        return self.commit[:7]

    @property
    def short_pull_latest(self) -> str:
        return self.pull_latest_sha[:7] if self.pull_latest_sha else ""

    @property
    def pending_toggle(self) -> bool | None:
        """Staged enable/disable, or None when it already matches ``active``.

        Toggling a row off and straight back on leaves ``pending_active`` set to
        what the PR already is; deploying that changes nothing, so nothing should
        offer it as a change.
        """
        return self.pending_active if self.pending_active != self.active else None

    @property
    def added_date(self) -> str:
        return self.added_at[:10] if self.added_at else ""


class TestingState(BaseModel):
    last_deploy_at: str  # ISO timestamp, empty if never deployed
    prs: list[TestingPR] = Field(default_factory=list)
    deployed_by: str = ""  # OL username of whoever clicked the last deploy; empty if never
    # Set only when Jenkins accepted a build; self-expires after _DEPLOY_WINDOW.
    deploy_started_at: str = ""
    # {pr number: title} of what the last deploy actually built — what
    # `live_now` renders from. Rows removed outright by code that predates
    # `pending_remove` survive only here, as read-only dropped rows.
    deployed: dict[int, str] = Field(default_factory=dict)


def _load_testing_state() -> TestingState | None:
    """Returns TestingState if state file exists, None otherwise."""
    if TESTING_STATE_FILE.exists():
        data = json.loads(TESTING_STATE_FILE.read_text())
        if isinstance(data, list):
            # Backward compat: old format was a bare array
            return TestingState(
                last_deploy_at="",
                prs=[TestingPR.model_validate(d) for d in data],
            )
        return TestingState.model_validate(data)
    return None


class TestingPRStatus(TestingPR):
    """A TestingPR merged with live GitHub drift info and derived flags."""

    head_sha: str = ""  # current branch HEAD (short SHA); empty if GitHub unavailable
    drift: int = -1  # commits the pinned commit is behind HEAD; -1 if unknown
    merged: bool = False  # PR has been merged into master
    is_new: bool = False  # added since the last deploy
    live_now: bool = False  # the last deploy put this PR on the box
    merge_conflict: bool = False  # the last deploy's merge of this PR conflicted, so it did not land
    closed: bool = False  # the PR was closed on GitHub without being merged; the next deploy drops it
    action: str = ""  # what the next deploy does with this row: add, pin, enable, disable, remove, or empty
    in_set: bool = True  # False for rows dropped from the set but still on the box


class PendingChange(BaseModel):
    """One staged change that the next deploy would apply."""

    pr: int
    title: str
    kind: str  # add, pin, enable, disable, remove
    detail: str = ""  # short SHA for add/pin changes; empty otherwise
    reason: str = ""  # why a removal is staged: merged, closed, or dropped; empty otherwise


class TestingStatus(BaseModel):
    """Status of the testing environment: what backs the /status deploy table and the JSON API.

    The deploy_* fields are filled from the latest Jenkins run by the FastAPI
    endpoint; they default empty so the compose path never needs them.
    """

    last_deploy_at: str  # ISO timestamp, empty if never deployed
    deployed_by: str = ""  # OL username of whoever clicked the last deploy; empty if never
    deploy_started_at: str  # ISO timestamp of the last deploy Jenkins accepted; empty if never
    deploying: bool  # whether a build is presumed still running (a time window, not a result)
    has_pending: bool  # whether there are pending changes ready to deploy
    prs: list[TestingPRStatus]  # the table rows, in-set and dropped alike
    pending_changes: list[PendingChange] = Field(default_factory=list)  # what the next deploy would apply, one entry per staged change
    deploy_result: str = ""  # latest ol-dev1-deploy run status; empty when Jenkins is unreachable
    deploy_finished_at: str = ""  # ISO end time of the latest Jenkins run; empty if running or unreachable
    deploy_stage: str = ""  # stage a running deploy is on; empty when not running or Jenkins is unreachable


def build_testing_status(state: TestingState, drift_info: dict, merge_conflicts: frozenset[int] = frozenset()) -> TestingStatus:
    """Compose the testing-environment status from persisted state and live drift info. Pure.

    Rows carry the live drift flags plus the derived per-row ``action`` and
    ``live_now`` the panel renders; rows dropped from the set but still on the
    box (``in_set=False``) are included so the table shows the full
    before/after picture. The plan (``pending_changes``) and deploy state are
    derived the same way the deploy handler applies them, so the table, the
    plan, and the JSON API can't drift apart.

    ``merge_conflicts`` is the set of PRs whose merge failed on the last deploy
    (read from the deploy status file); their rows carry ``merge_conflict`` so
    the panel can show they did not land.
    """
    last_deploy = state.last_deploy_at
    pending_changes = _pending_changes(state, drift_info)
    # The row chip is the first change the plan schedules for that PR. The plan
    # emits each PR's changes in _CHANGE_ORDER, so the first entry carries the
    # same precedence the deleted _row_action applied — one source of truth.
    actions: dict[int, str] = {}
    for change in pending_changes:
        actions.setdefault(change.pr, change.kind)
    remaining = {p.pr for p in state.prs}
    prs = [
        TestingPRStatus(
            **p.model_dump(),
            head_sha=drift_info.get(p.pr, {}).get("head_sha", ""),
            drift=drift_info.get(p.pr, {}).get("drift", -1),
            merged=drift_info.get(p.pr, {}).get("merged", False),
            is_new=bool(last_deploy and p.added_at > last_deploy),
            live_now=_live_now(state, p),
            merge_conflict=p.pr in merge_conflicts,
            closed=drift_info.get(p.pr, {}).get("closed", False),
            action=actions.get(p.pr, ""),
            in_set=True,
        )
        for p in state.prs
    ]
    # Deployed but no longer in the set (removed outright by pre-`pending_remove`
    # code): the deploy drops them from the box, so they get a read-only row
    # flagged for removal rather than vanishing.
    for pr, title in state.deployed.items():
        if pr not in remaining:
            prs.append(
                TestingPRStatus(
                    pr=pr,
                    title=title,
                    commit="",
                    active=False,
                    added_at="",
                    added_by="",
                    pull_latest_sha="",
                    pending_active=None,
                    pending_remove=False,
                    author="",
                    author_avatar="",
                    assignee="",
                    assignee_avatar="",
                    head_sha="",
                    drift=-1,
                    merged=False,
                    is_new=False,
                    live_now=True,
                    action="remove",
                    in_set=False,
                )
            )
    prs.sort(key=lambda row: row.pr)
    return TestingStatus(
        last_deploy_at=last_deploy,
        deployed_by=state.deployed_by,
        deploy_started_at=state.deploy_started_at,
        deploying=_is_deploying(state),
        pending_changes=pending_changes,
        has_pending=bool(pending_changes),
        prs=prs,
    )


async def load_testing_status_async() -> TestingStatus | None:
    """Load the state file and live drift info; None if there is no state file.

    Async so the FastAPI endpoint can await it: the GitHub drift fetch below
    runs on the event loop instead of blocking it. Sync callers use the
    ``load_testing_status`` bridge wrapper instead.
    """
    if (state := _load_testing_state()) is None:
        return None
    drift_info, _ = await _get_drift_info_async(state)
    return build_testing_status(state, drift_info, merge_conflicts=_merge_conflicted_prs())


def _parse_pr_number(value: str) -> int:
    """Parse one token as a PR number, accepting ``#123`` or a PR URL."""
    value = value.strip()
    if "/issues/" in value:
        raise ValueError(f"Not a PR URL (looks like an issue): {value!r}")
    if m := re.search(r"/pull/(\d+)", value):
        return int(m.group(1))
    return int(value.lstrip("#"))


def parse_pr_numbers(value: str | list[str]) -> list[int]:
    """Split whitespace/comma-separated PR input into numbers, dropping bad tokens.

    The panel's add input accepts ``"12914 13269"``, ``"12914,13269"``,
    ``"#12914"``, and PR URLs interchangeably. Unparsable tokens (including
    issue URLs) are skipped; input with no valid PR yields an empty list so the
    caller can reject it rather than guessing.
    """
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    numbers: list[int] = []
    for token in re.split(r"[\s,]+", " ".join(str(item) for item in value).strip()):
        if token:
            with contextlib.suppress(ValueError, AttributeError):
                numbers.append(_parse_pr_number(token))
    return numbers


async def add_prs(pr_numbers: list[int], username: str) -> dict:
    """Append new PRs to the testing set and clear any staged removal on re-adds."""
    state = _load_testing_state() or TestingState(last_deploy_at="", prs=[])
    existing = {p.pr for p in state.prs}
    # Re-adding a PR whose removal is staged is an undo, not a new add.
    for p in state.prs:
        if p.pr in pr_numbers:
            p.pending_remove = False
    failed: dict[int, str] = {}
    added: dict[int, GitHubPRInfo] = {}

    for pr_number in pr_numbers:
        if pr_number in existing:
            continue
        try:
            info = await _get_pr_info_async(pr_number)
        except PRNotFoundError:
            failed[pr_number] = "not_found"
            continue
        except GitHubUnavailableError:
            # GitHub unreachable or rate-limited — never pretend the add landed.
            # Reporting the reason per PR lets the panel keep the input and say
            # which number was rejected.
            failed[pr_number] = "unavailable"
            continue
        state.prs.append(TestingPR.from_github(info, username))
        existing.add(pr_number)
        added[pr_number] = info
    _save_testing_state(state)
    _extend_drift_cache(added)
    if failed:
        return {"ok": False, "error": "add_failed", "failed_prs": failed}
    return {"ok": True}


# A failed merge is recorded two ways, depending on which machinery wrote the
# file: git's own message when the transcript captures merge output, or the
# deploy script's summary (see scripts/make-integration-branch.sh):
# "Merge conflict for PR #13370 (pinned <sha>) — skipping". Match both so a
# real conflict always lights the row.
_MERGE_CONFLICT_PREFIXES = ("Automatic merge failed", "Merge conflict for PR #")


def _merge_conflicted_prs() -> frozenset[int]:
    """PRs whose merge failed on the last deploy, per the deploy status file.

    Reads the same ``_dev-merged_status.txt`` that powers the legacy "Last
    Build Result" table: a PR row whose status says the merge failed means the
    deploy skipped it, so it never landed on the box.
    """
    dms = get_dev_merged_status()
    if not dms:
        return frozenset()
    conflicted: set[int] = set()
    for pr in dms.pr_statuses:
        if not pr.status.startswith(_MERGE_CONFLICT_PREFIXES):
            continue
        if pr.pull_id:
            conflicted.add(pr.pull_id)
        # Fallback: the summary message names the PR when the pull_line carries
        # no "origin pull/N/head" line to parse a number from.
        elif m := re.search(r"Merge conflict for PR #(\d+)", pr.status):
            conflicted.add(int(m.group(1)))
    return frozenset(conflicted)


def _save_testing_state(state: TestingState) -> None:
    # Atomic replace: the FastAPI GET and the web.py POST handlers both write
    # this file, and a torn write would corrupt the state.
    tmp = TESTING_STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state.model_dump(), indent=2))
    tmp.replace(TESTING_STATE_FILE)


def _ensure_testing_state_file() -> None:
    """Create an empty testing state file at startup if missing.

    Keeps the /status page and the testing-status API functional from first
    boot without a manually created _testing-prs.json. Never overwrites
    existing state.
    """
    if not TESTING_STATE_FILE.exists():
        TESTING_STATE_FILE.write_text(json.dumps({"last_deploy_at": "", "prs": []}, indent=2))


def _is_maintainer() -> bool:
    user = get_current_user()
    return bool(user and user.is_maintainer())


# One pooled client per event loop. The drift fan-out makes up to two GitHub
# calls per PR, and a fresh AsyncClient per call would pay a TCP + TLS
# handshake every time. cache_per_event_loop keeps a separate pool per loop,
# since AsyncBridge's background loop and FastAPI's can't share one.
get_github_client = cache_per_event_loop(lambda: httpx.AsyncClient(timeout=5.0))


async def _github_get_async(path: str) -> dict:
    """GET a GitHub API path; raises httpx.HTTPError (network or non-2xx) on failure."""
    url = f"{_GITHUB_API_BASE}/{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "openlibrary-status",
    }
    if token := getattr(config, "github_api_token", None):
        headers["Authorization"] = f"Bearer {token}"
    resp = await get_github_client().get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


async def _get_drift_info_async(state: TestingState, persist: bool = True) -> tuple[dict, bool]:
    """Return (drift_dict, from_cache). Checks memcache first; fetches GitHub on miss.

    Keys are int PR numbers. JSON round-trip via memcache stringifies keys, so we
    re-cast on read.

    On a cache miss, also refreshes title/author/assignee on each TestingPR in-place
    and, unless ``persist=False``, saves the state file if anything changed. The
    deploy path passes ``persist=False`` so its metadata refresh can never write
    staged-but-untriggered changes to disk.

    Per-PR fetches run concurrently (asyncio.gather) — with a handful of PRs,
    sequential awaits would stack each GitHub round-trip.
    """
    mc = cache.get_memcache()
    if (cached := mc.get(_DRIFT_CACHE_KEY)) is not None:
        return {int(k): v for k, v in cached.items()}, True
    drift = {}
    state_changed = False
    infos = await asyncio.gather(*(_get_pr_drift_async(p) for p in state.prs))
    for p, info in zip(state.prs, infos):
        drift[p.pr] = {k: info[k] for k in ("head_sha", "drift", "merged", "closed")}
        for attr in ("title", "author", "author_avatar", "assignee", "assignee_avatar"):
            new_val = info.get(attr, "")
            if new_val and getattr(p, attr) != new_val:
                setattr(p, attr, new_val)
                state_changed = True
    if state_changed and persist:
        _save_testing_state(state)
    mc.set(_DRIFT_CACHE_KEY, drift, expires=_DRIFT_CACHE_TTL)
    return drift, False


def _evict_drift_cache() -> None:
    cache.get_memcache().delete(_DRIFT_CACHE_KEY)


def _extend_drift_cache(new_prs: dict[int, GitHubPRInfo]) -> None:
    """Record freshly added PRs in the drift cache, leaving the rest of it intact.

    Adding a PR says nothing about the drift of the PRs already in the set, so
    evicting the whole cache would make the panel's next read refetch every row
    over GitHub — the cost is in the fan-out, not the added row. Each new PR is
    pinned to its current head, so its drift is already known: 0 behind, not
    merged. ``merged``/``closed`` are defaults rather than observations —
    ``_get_pr_info_async`` doesn't report them — and the next fetch replaces
    them within ``_DRIFT_CACHE_TTL``, the same staleness window every other
    cached row already lives with.

    A cold cache is a no-op: the next read fetches the full set anyway.
    """
    if not new_prs:
        return
    mc = cache.get_memcache()
    if (cached := mc.get(_DRIFT_CACHE_KEY)) is None:
        return
    for pr_number, info in new_prs.items():
        cached[str(pr_number)] = {
            "head_sha": info.head_sha[:7],
            "drift": 0,
            "merged": False,
            "closed": False,
        }
    mc.set(_DRIFT_CACHE_KEY, cached, expires=_DRIFT_CACHE_TTL)


async def _get_pr_info_async(pr_number: int) -> GitHubPRInfo:
    """Fetch title, HEAD SHA, author, and assignee for a PR from GitHub.

    Raises ``PRNotFoundError`` on a 404 and ``GitHubUnavailableError`` for rate
    limits, network failures, or an unparsable body — so callers can tell a bad
    PR number from a GitHub outage, and a returned value is always real data.
    """
    try:
        pr = await _github_get_async(f"pulls/{pr_number}")
        user = pr.get("user") or {}
        assignee = pr.get("assignee") or {}
        return GitHubPRInfo(
            pr=pr_number,
            title=pr.get("title") or f"PR #{pr_number}",
            head_sha=pr["head"]["sha"],
            author=user.get("login", ""),
            author_avatar=user.get("avatar_url", ""),
            assignee=assignee.get("login", ""),
            assignee_avatar=assignee.get("avatar_url", ""),
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise PRNotFoundError(f"PR #{pr_number} not found") from e
        raise GitHubUnavailableError(f"GitHub returned {e.response.status_code} for PR #{pr_number}") from e
    except (httpx.HTTPError, KeyError, ValueError) as e:
        raise GitHubUnavailableError(f"Could not fetch PR #{pr_number}") from e


async def _get_pr_drift_async(pr: TestingPR) -> dict:
    """Fetch live drift info + metadata for a PR from GitHub.

    Returns head_sha, drift, merged plus title/author/assignee so callers can
    refresh state without a second API call.
    """
    try:
        gh = await _github_get_async(f"pulls/{pr.pr}")
        head_sha = gh["head"]["sha"]
        merged = bool(gh.get("merged") or gh.get("merged_at"))
        stored = pr.commit.strip()
        if head_sha == stored or (len(stored) < 40 and head_sha.startswith(stored)):
            drift = 0
        else:
            try:
                cmp = await _github_get_async(f"compare/{stored}...{head_sha}")
                drift = cmp.get("ahead_by", -1)
            except httpx.HTTPError, ValueError:
                drift = -1
        user = gh.get("user") or {}
        assignee = gh.get("assignee") or {}
        return {
            "head_sha": head_sha[:7],
            "drift": drift,
            "merged": merged,
            # A merge is itself a close, so "closed" means closed without merging.
            "closed": gh.get("state") == "closed" and not merged,
            "title": gh.get("title", f"PR #{pr.pr}"),
            "author": user.get("login", ""),
            "author_avatar": user.get("avatar_url", ""),
            "assignee": assignee.get("login", ""),
            "assignee_avatar": assignee.get("avatar_url", ""),
        }
    except httpx.HTTPError, KeyError, ValueError:
        return {
            "head_sha": "",
            "drift": -1,
            "merged": False,
            "closed": False,
            "title": "",
            "author": "",
            "author_avatar": "",
            "assignee": "",
            "assignee_avatar": "",
        }


# Sync bridge wrappers: the remaining web.py action handlers reach the async
# implementations above through AsyncBridge's background event loop instead of
# duplicating them. FastAPI should call the ``*_async`` versions directly and
# await them (see openlibrary/utils/async_utils.py).
_get_pr_info = async_bridge.wrap(_get_pr_info_async)
_get_drift_info = async_bridge.wrap(_get_drift_info_async)
load_testing_status = async_bridge.wrap(load_testing_status_async)


@public
def get_git_revision_short_hash():
    return status_info.get("Software version") if status_info and isinstance(status_info, dict) else None


def get_features_enabled():
    return config.features


def get_features_table() -> list[dict[str, str]]:
    """Build a list of enabled feature flags."""
    infogami_dict = config.features  # type: ignore[attr-defined]
    features_table = []
    for feature in sorted(infogami_dict.keys()):
        infogami_value = infogami_dict.get(feature)
        if isinstance(infogami_value, dict):
            infogami_str = f"usergroup: {infogami_value.get('usergroup', '?')}"
        else:
            infogami_str = str(infogami_value) if infogami_value is not None else ""
        features_table.append({"feature": feature, "infogami": infogami_str})
    return features_table


def setup():
    "Basic startup status for the server"
    if get_ol_env().LOCAL_DEV:
        _ensure_testing_state_file()
    global status_info
    host = socket.gethostname()
    status_info = {
        "Software version": get_software_version(),
        "Python version": sys.version.split()[0],
        "Host": host,
        "Start time": datetime.datetime.now(datetime.UTC),
    }

    # Host is e.g. ol-web4.blah.archive.org ; we just want the first subdomain
    first_subdomain = host.split(".")[0] or "unknown"
    stats.increment("ol.servers.%s.started" % first_subdomain)
