import contextlib
import datetime
import functools
import http.client
import json
import re
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import web

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import public, render_template
from openlibrary.accounts import get_current_user
from openlibrary.core import cache, stats
from openlibrary.core.env import get_ol_env
from openlibrary.utils import get_software_version

status_info: dict[str, Any] = {}

TESTING_STATE_FILE = Path("./_testing-prs.json")
_GITHUB_API_BASE = "https://api.github.com/repos/internetarchive/openlibrary"
_JENKINS_URL = "https://jenkins.openlibrary.org/job/testing-deploy/buildWithParameters"
_JENKINS_JOB_URL = "https://jenkins.openlibrary.org/job/ol-dev1-deploy%20(internal)/"
_DRIFT_CACHE_KEY = "status.github_pr_drift"
_DRIFT_CACHE_TTL = 5 * 60  # 5 minutes
# Jenkins never calls back, so a triggered deploy is only ever presumed to be
# running. After this long we stop claiming it is, without claiming it worked.
_DEPLOY_WINDOW = 10 * 60  # 10 minutes
# Reading order for the pending-change plan: additions first, removals last.
_CHANGE_ORDER = {"add": 0, "pin": 1, "enable": 2, "disable": 3, "remove": 4}


class status(delegate.page):
    def GET(self):
        is_maintainer_user = _is_maintainer()
        has_testing_state = _load_testing_state() is not None
        # The panel reads its state from FastAPI in the browser. Keep only this
        # lightweight existence/permission check so non-maintainers do not get
        # a shell that would immediately produce a 403 from the JSON endpoint.
        show_testing = has_testing_state and is_maintainer_user
        return render_template(
            "status",
            status_info,
            features_table=get_features_table(),
            dev_merged_status=get_dev_merged_status(),
            is_maintainer=is_maintainer_user,
            has_testing_state=has_testing_state,
            show_testing=show_testing,
            jenkins_job_url=_JENKINS_JOB_URL,
        )


class status_add(delegate.page):
    path = "/status/add"

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        i = web.input(pr="")
        raw = re.split(r"[\s,]+", i.pr.strip())
        pr_numbers = []
        for val in raw:
            if val:
                with contextlib.suppress(ValueError, AttributeError):
                    pr_numbers.append(_parse_pr_number(val))
        if not pr_numbers:
            raise web.badrequest()
        state = _load_testing_state() or TestingState(last_deploy_at="", prs=[])
        existing = {p.pr for p in state.prs}
        user = get_current_user()
        failed = []
        for pr_number in pr_numbers:
            if pr_number not in existing:
                info = _get_pr_info(pr_number)
                if info.get("error"):
                    # GitHub unreachable, rate-limited, or an invalid PR — never
                    # pretend the add landed. The redirect marker lets the panel
                    # keep the input so the failure is visible.
                    failed.append(pr_number)
                    continue
                state.prs.append(
                    TestingPR(
                        pr=pr_number,
                        commit=info["head_sha"],
                        active=True,
                        title=info["title"],
                        added_at=datetime.datetime.now(datetime.UTC).isoformat(),
                        added_by=user.key.split("/")[-1] if user else "",
                        author=info["author"],
                        author_avatar=info["author_avatar"],
                        assignee=info["assignee"],
                        assignee_avatar=info["assignee_avatar"],
                    )
                )
                existing.add(pr_number)
        _save_testing_state(state)
        _evict_drift_cache()
        if failed:
            raise web.seeother("/status?add_failed=1")
        raise web.seeother("/status")


class status_remove(delegate.page):
    path = "/status/remove"

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        i = web.input(prs=[])
        to_remove = {int(p) for p in i.prs}
        if state := _load_testing_state():
            state.prs = [p for p in state.prs if p.pr not in to_remove]
            _save_testing_state(state)
        raise web.seeother("/status")


class status_enable(delegate.page):
    path = "/status/enable"

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        i = web.input(prs=[])
        to_enable = {int(p) for p in i.prs}
        state = _load_testing_state()
        if not state or not to_enable:
            raise web.seeother("/status")
        for p in state.prs:
            if p.pr in to_enable:
                p.pending_active = True
        _save_testing_state(state)
        raise web.seeother("/status")


class status_disable(delegate.page):
    path = "/status/disable"

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        i = web.input(prs=[])
        to_disable = {int(p) for p in i.prs}
        state = _load_testing_state()
        if not state or not to_disable:
            raise web.seeother("/status")
        for p in state.prs:
            if p.pr in to_disable:
                p.pending_active = False
        _save_testing_state(state)
        raise web.seeother("/status")


class status_pull_latest(delegate.page):
    path = "/status/pull-latest"

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        i = web.input(prs=[])
        to_update = {int(p) for p in i.prs}
        state = _load_testing_state()
        if not state or not to_update:
            raise web.seeother("/status")
        for p in state.prs:
            if p.pr in to_update:
                info = _get_pr_info(p.pr)
                if info["head_sha"] and info["head_sha"] != p.commit:
                    p.pull_latest_sha = info["head_sha"]
        _save_testing_state(state)
        raise web.seeother("/status")


class status_deploy(delegate.page):
    path = "/status/deploy"

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        state = _load_testing_state()
        if not state:
            raise web.seeother("/status")
        # Decide merged-removals on the *un-mutated* state — `merged` is
        # independent of staged pins/toggles — and with persist=False, so the
        # drift metadata refresh can never write staged changes to disk before
        # Jenkins accepts the build.
        drift_info, _ = _get_drift_info(state, persist=False)
        state.prs = [p for p in state.prs if not drift_info.get(p.pr, {}).get("merged", False)]
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
        outcome = _trigger_rebuild(state)
        if outcome == "failed":
            raise web.seeother("/status?deploy_failed=1")
        state.last_deploy_at = datetime.datetime.now(datetime.UTC).isoformat()
        # What this build puts on the box: active PRs only, the same filter
        # _trigger_rebuild sends. Recorded so a later removal has a set to be
        # missing from — nothing else survives one.
        state.deployed = {p.pr: p.title for p in state.prs if p.active}
        if outcome == "triggered":
            state.deploy_started_at = state.last_deploy_at
        _save_testing_state(state)
        _evict_drift_cache()
        raise web.seeother("/status?deploy_triggered=1" if outcome == "triggered" else "/status?deploy_unconfigured=1")


class status_refresh(delegate.page):
    path = "/status/refresh"

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        _evict_drift_cache()
        raise web.seeother("/status?drift_refreshed=1")


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


def _pending_changes(state: TestingState, drift_info: dict) -> list[dict]:
    """The plan: what deploying would change, one entry per staged change.

    Every row action writes staged intent that only status_deploy applies, so
    this walks the same fields it flushes. A PR merged to master is dropped by
    the deploy regardless of what else is staged on it, so it yields one
    ``remove`` and nothing more.

    Removal is the one action that stages nothing: it deletes the row. Those are
    recovered at the end by diffing ``state.deployed`` — what the last deploy
    built — against what is left.
    """
    last_deploy = state.last_deploy_at
    changes: list[dict[str, Any]] = []
    for p in state.prs:
        entry = {"pr": p.pr, "title": p.title, "reason": ""}
        if drift_info.get(p.pr, {}).get("merged", False):
            changes.append({**entry, "kind": "remove", "reason": "merged", "detail": ""})
            continue
        if not last_deploy or p.added_at > last_deploy:
            # A pin staged on a PR that isn't live yet isn't a separate change:
            # it's just the SHA the PR lands at, so report the effective one.
            changes.append({**entry, "kind": "add", "detail": p.short_pull_latest or p.short_commit})
        elif p.pull_latest_sha:
            changes.append({**entry, "kind": "pin", "detail": p.short_pull_latest})
        if (toggle := p.pending_toggle) is not None:
            changes.append({**entry, "kind": "enable" if toggle else "disable", "detail": ""})
    # Deployed but no longer in the set: removed, and still on the box until the
    # next deploy drops it. State files written before `deployed` existed start
    # empty here, so their first deploy is what makes removals visible.
    # ``reason`` separates these from the merged ones above, which are the same
    # kind for a different cause and must not borrow each other's wording.
    remaining = {p.pr for p in state.prs}
    for pr, title in state.deployed.items():
        if pr not in remaining:
            changes.append({"pr": pr, "title": title, "kind": "remove", "reason": "dropped", "detail": ""})
    changes.sort(key=lambda c: (_CHANGE_ORDER[c["kind"]], c["pr"]))
    return changes


@functools.cache
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


@dataclass
class TestingPR:
    pr: int
    commit: str  # pinned commit SHA (full)
    active: bool
    title: str
    added_at: str  # ISO timestamp
    added_by: str  # OL username
    pull_latest_sha: str = ""  # pending SHA from "Fetch Latest"; applied on deploy
    pending_active: bool | None = None  # pending enable/disable; applied on deploy
    author: str = ""  # GitHub login of PR author
    author_avatar: str = ""  # GitHub avatar URL (append &s=N for sizing)
    assignee: str = ""  # GitHub login of assignee, empty if unassigned
    assignee_avatar: str = ""  # GitHub avatar URL for assignee

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

    def to_dict(self) -> dict:
        d = {
            "pr": self.pr,
            "commit": self.commit,
            "active": self.active,
            "title": self.title,
            "added_at": self.added_at,
            "added_by": self.added_by,
        }
        if self.pull_latest_sha:
            d["pull_latest_sha"] = self.pull_latest_sha
        if self.pending_toggle is not None:
            d["pending_active"] = self.pending_toggle
        if self.author:
            d["author"] = self.author
        if self.author_avatar:
            d["author_avatar"] = self.author_avatar
        if self.assignee:
            d["assignee"] = self.assignee
        if self.assignee_avatar:
            d["assignee_avatar"] = self.assignee_avatar
        return d

    @classmethod
    def from_dict(cls, d: dict) -> TestingPR:
        return cls(
            pr=d["pr"],
            commit=d["commit"],
            active=d.get("active", True),
            title=d.get("title", f"PR #{d['pr']}"),
            added_at=d.get("added_at", ""),
            added_by=d.get("added_by", ""),
            pull_latest_sha=d.get("pull_latest_sha", ""),
            pending_active=d.get("pending_active"),
            author=d.get("author", ""),
            author_avatar=d.get("author_avatar", ""),
            assignee=d.get("assignee", ""),
            assignee_avatar=d.get("assignee_avatar", ""),
        )


@dataclass
class TestingState:
    last_deploy_at: str  # ISO timestamp, empty if never deployed
    prs: list[TestingPR] = field(default_factory=list)
    # Set only when Jenkins accepted a build; self-expires after _DEPLOY_WINDOW.
    deploy_started_at: str = ""
    # {pr number: title} of what the last deploy actually built. Removing a PR
    # deletes it from `prs` outright, so this is the only record that the box is
    # still running it — without it a removal is invisible and undeployable.
    deployed: dict[int, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "last_deploy_at": self.last_deploy_at,
            "deploy_started_at": self.deploy_started_at,
            "prs": [p.to_dict() for p in self.prs],
            # JSON object keys are strings; from_dict puts them back to int.
            "deployed": {str(pr): title for pr, title in self.deployed.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> TestingState:
        return cls(
            last_deploy_at=d.get("last_deploy_at", ""),
            prs=[TestingPR.from_dict(p) for p in d.get("prs", [])],
            deploy_started_at=d.get("deploy_started_at", ""),
            deployed={int(pr): title for pr, title in d.get("deployed", {}).items()},
        )


def _load_testing_state() -> TestingState | None:
    """Returns TestingState if state file exists, None otherwise."""
    if TESTING_STATE_FILE.exists():
        data = json.loads(TESTING_STATE_FILE.read_text())
        if isinstance(data, list):
            # Backward compat: old format was a bare array
            return TestingState(
                last_deploy_at="",
                prs=[TestingPR.from_dict(d) for d in data],
            )
        return TestingState.from_dict(data)
    return None


@dataclass
class TestingPRStatus(TestingPR):
    """A TestingPR merged with live GitHub drift info and derived flags."""

    head_sha: str = ""  # current branch HEAD (short SHA); empty if GitHub unavailable
    drift: int = -1  # commits the pinned commit is behind HEAD; -1 if unknown
    merged: bool = False  # PR has been merged into master
    is_new: bool = False  # added since the last deploy
    live_now: bool = False  # the last deploy put this PR on the box
    action: str = ""  # what the next deploy does with this row: add, pin, enable, disable, remove, or empty
    in_set: bool = True  # False for rows dropped from the set but still on the box


@dataclass
class TestingStatus:
    """Status of the testing environment: what backs the /status deploy table and the JSON API."""

    last_deploy_at: str  # ISO timestamp, empty if never deployed
    deploy_started_at: str  # ISO timestamp of the last deploy Jenkins accepted; empty if never
    deploying: bool  # whether a build is presumed still running (a time window, not a result)
    has_pending: bool  # whether there are pending changes ready to deploy
    pending_changes: list[dict]  # what the next deploy would apply, one entry per staged change
    prs: list[TestingPRStatus]


def build_testing_status(state: TestingState, drift_info: dict) -> TestingStatus:
    """Compose the testing-environment status from persisted state and live drift info. Pure.

    Rows carry the live drift flags plus the derived per-row ``action`` and
    ``live_now`` the panel renders; rows dropped from the set but still on the
    box (``in_set=False``) are included so the table shows the full
    before/after picture. The plan (``pending_changes``) and deploy state are
    derived the same way the deploy handler applies them, so the table, the
    plan, and the JSON API can't drift apart.
    """
    last_deploy = state.last_deploy_at
    pending_changes = _pending_changes(state, drift_info)
    # The row chip is the first change the plan schedules for that PR. The plan
    # emits each PR's changes in _CHANGE_ORDER, so the first entry carries the
    # same precedence the deleted _row_action applied — one source of truth.
    actions: dict[int, str] = {}
    for change in pending_changes:
        actions.setdefault(change["pr"], change["kind"])
    remaining = {p.pr for p in state.prs}
    # The `deployed` record postdates most state files, so an empty one means
    # "pre-record" rather than "nothing was ever deployed": infer what the last
    # deploy built the same way _pending_changes does — anything added before it
    # was part of it. A populated record is authoritative (it also catches PRs
    # deployed then removed, which no longer exist in prs).
    deployed_record = bool(state.deployed)
    prs = [
        TestingPRStatus(
            **asdict(p),
            head_sha=drift_info.get(p.pr, {}).get("head_sha", ""),
            drift=drift_info.get(p.pr, {}).get("drift", -1),
            merged=drift_info.get(p.pr, {}).get("merged", False),
            is_new=bool(last_deploy and p.added_at > last_deploy),
            live_now=p.pr in state.deployed or (not deployed_record and bool(last_deploy and p.added_at <= last_deploy)),
            action=actions.get(p.pr, ""),
            in_set=True,
        )
        for p in state.prs
    ]
    # Deployed but no longer in the set: the deploy drops them from the box, so
    # they get a read-only row flagged for removal rather than vanishing.
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
        deploy_started_at=state.deploy_started_at,
        deploying=_is_deploying(state),
        pending_changes=pending_changes,
        has_pending=bool(pending_changes),
        prs=prs,
    )


def load_testing_status() -> TestingStatus | None:
    """Load the state file and live drift info; None if there is no state file."""
    if (state := _load_testing_state()) is None:
        return None
    drift_info, _ = _get_drift_info(state)
    return build_testing_status(state, drift_info)


def _save_testing_state(state: TestingState) -> None:
    # Atomic replace: the FastAPI GET and the web.py POST handlers both write
    # this file, and a torn write would corrupt the state.
    tmp = TESTING_STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state.to_dict(), indent=2))
    tmp.replace(TESTING_STATE_FILE)
    get_dev_merged_status.cache_clear()


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


def _github_get(path: str) -> dict:
    url = f"{_GITHUB_API_BASE}/{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "openlibrary-status",
    }
    if token := getattr(config, "github_api_token", None):
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _get_drift_info(state: TestingState, persist: bool = True) -> tuple[dict, bool]:
    """Return (drift_dict, from_cache). Checks memcache first; fetches GitHub on miss.

    Keys are int PR numbers. JSON round-trip via memcache stringifies keys, so we
    re-cast on read.

    On a cache miss, also refreshes title/author/assignee on each TestingPR in-place
    and, unless ``persist=False``, saves the state file if anything changed. The
    deploy path passes ``persist=False`` so its metadata refresh can never write
    staged-but-untriggered changes to disk.
    """
    mc = cache.get_memcache()
    if (cached := mc.get(_DRIFT_CACHE_KEY)) is not None:
        return {int(k): v for k, v in cached.items()}, True
    drift = {}
    state_changed = False
    for p in state.prs:
        info = _get_pr_drift(p)
        drift[p.pr] = {k: info[k] for k in ("head_sha", "drift", "merged")}
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


def _get_pr_info(pr_number: int) -> dict:
    """Fetch title, HEAD SHA, author, and assignee for a PR from GitHub.

    On failure ``error`` says why — ``not_found`` for a 404, ``unavailable`` for
    rate limits/network/parse errors — so callers can tell a bad PR number from
    a GitHub outage instead of treating both as "no such PR".
    """
    try:
        pr = _github_get(f"pulls/{pr_number}")
        user = pr.get("user") or {}
        assignee = pr.get("assignee") or {}
        return {
            "title": pr.get("title", f"PR #{pr_number}"),
            "head_sha": pr["head"]["sha"],
            "author": user.get("login", ""),
            "author_avatar": user.get("avatar_url", ""),
            "assignee": assignee.get("login", ""),
            "assignee_avatar": assignee.get("avatar_url", ""),
            "error": "",
        }
    except urllib.error.HTTPError as e:
        return {
            "title": f"PR #{pr_number}",
            "head_sha": "",
            "author": "",
            "author_avatar": "",
            "assignee": "",
            "assignee_avatar": "",
            "error": "not_found" if e.code == 404 else "unavailable",
        }
    except urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError:
        return {
            "title": f"PR #{pr_number}",
            "head_sha": "",
            "author": "",
            "author_avatar": "",
            "assignee": "",
            "assignee_avatar": "",
            "error": "unavailable",
        }


def _get_pr_drift(pr: TestingPR) -> dict:
    """Fetch live drift info + metadata for a PR from GitHub.

    Returns head_sha, drift, merged plus title/author/assignee so callers can
    refresh state without a second API call.
    """
    try:
        gh = _github_get(f"pulls/{pr.pr}")
        head_sha = gh["head"]["sha"]
        merged = bool(gh.get("merged") or gh.get("merged_at"))
        stored = pr.commit.strip()
        if head_sha == stored or (len(stored) < 40 and head_sha.startswith(stored)):
            drift = 0
        else:
            try:
                cmp = _github_get(f"compare/{stored}...{head_sha}")
                drift = cmp.get("ahead_by", -1)
            except urllib.error.URLError, ValueError, json.JSONDecodeError:
                drift = -1
        user = gh.get("user") or {}
        assignee = gh.get("assignee") or {}
        return {
            "head_sha": head_sha[:7],
            "drift": drift,
            "merged": merged,
            "title": gh.get("title", f"PR #{pr.pr}"),
            "author": user.get("login", ""),
            "author_avatar": user.get("avatar_url", ""),
            "assignee": assignee.get("login", ""),
            "assignee_avatar": assignee.get("avatar_url", ""),
        }
    except urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError:
        return {
            "head_sha": "",
            "drift": -1,
            "merged": False,
            "title": "",
            "author": "",
            "author_avatar": "",
            "assignee": "",
            "assignee_avatar": "",
        }


def _parse_pr_number(value: str) -> int:
    value = value.strip()
    if "/issues/" in value:
        raise ValueError(f"Not a PR URL (looks like an issue): {value!r}")
    if m := re.search(r"/pull/(\d+)", value):
        return int(m.group(1))
    return int(value.lstrip("#"))


def _trigger_rebuild(state: TestingState) -> str:
    """Call Jenkins to rebuild from ``state``.

    Returns ``"triggered"``, ``"failed"`` (Jenkins unreachable or refused), or
    ``"unconfigured"`` when there is no jenkins_token, as in local dev.
    """
    token = getattr(config, "jenkins_token", None)
    if not token:
        return "unconfigured"
    lines = "\n".join(f"origin pull/{p.pr}/head  # {p.title}" for p in state.prs if p.active)
    url = f"{_JENKINS_URL}?{urlencode({'token': token, 'GH_REPO_AND_BRANCH': lines})}"
    try:
        urllib.request.urlopen(url, timeout=10)
        return "triggered"
    except OSError, http.client.HTTPException, ValueError:
        # OSError covers URLError/HTTPError plus the read-timeout and dropped-
        # connection errors that escape urlopen unwrapped.
        return "failed"


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
