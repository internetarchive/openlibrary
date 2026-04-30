import contextlib
import datetime
import functools
import json
import re
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import web
from infogami import config
from infogami.utils import delegate
from infogami.utils.view import public, render_template

from openlibrary.accounts import get_current_user
from openlibrary.core import cache, stats
from openlibrary.utils import get_software_version

status_info: dict[str, Any] = {}
feature_flags: dict[str, Any] = {}

TESTING_STATE_FILE = Path("./_testing-prs.json")
_GITHUB_API_BASE = "https://api.github.com/repos/internetarchive/openlibrary"
_JENKINS_URL = "https://jenkins.openlibrary.org/job/testing-deploy/buildWithParameters"
_JENKINS_JOB_URL = "https://jenkins.openlibrary.org/job/ol-dev1-deploy%20(internal)/"
_DRIFT_CACHE_KEY = "status.github_pr_drift"
_DRIFT_CACHE_TTL = 5 * 60  # 5 minutes


class status(delegate.page):
    def GET(self):
        testing_state = _load_testing_state()
        is_maintainer_user = _is_maintainer()
        drift_info = {}
        if testing_state:
            drift_info, _ = _get_drift_info(testing_state)
        show_testing = testing_state is not None and is_maintainer_user
        last_deploy = testing_state.last_deploy_at if testing_state else ""
        has_pending = bool(testing_state) and any(
            p.pull_latest_sha or p.pending_active is not None or drift_info.get(p.pr, {}).get("merged", False) or not last_deploy or p.added_at > last_deploy
            for p in testing_state.prs
        )
        i = web.input(deploy_triggered=None, drift_refreshed=None)
        return render_template(
            "status",
            status_info,
            feature_flags,
            dev_merged_status=get_dev_merged_status(),
            testing_state=testing_state,
            drift_info=drift_info,
            is_maintainer=is_maintainer_user,
            show_testing=show_testing,
            deploy_triggered=bool(i.deploy_triggered),
            drift_refreshed=bool(i.drift_refreshed),
            jenkins_job_url=_JENKINS_JOB_URL,
            has_pending=has_pending,
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
        for pr_number in pr_numbers:
            if pr_number not in existing:
                info = _get_pr_info(pr_number)
                if not info["head_sha"]:
                    continue  # GitHub API unavailable or invalid PR
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
        # Apply all pending changes before deploying
        for p in state.prs:
            if p.pull_latest_sha:
                p.commit = p.pull_latest_sha
                p.pull_latest_sha = ""
            if p.pending_active is not None:
                p.active = p.pending_active
                p.pending_active = None
        # Remove PRs that have already been merged into master
        drift_info, _ = _get_drift_info(state)
        state.prs = [p for p in state.prs if not drift_info.get(p.pr, {}).get("merged", False)]
        state.last_deploy_at = datetime.datetime.now(datetime.UTC).isoformat()
        _save_testing_state(state)
        _evict_drift_cache()
        triggered = _trigger_rebuild()
        raise web.seeother("/status?deploy_triggered=1" if triggered else "/status")


class status_refresh(delegate.page):
    path = "/status/refresh"

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        _evict_drift_cache()
        raise web.seeother("/status?drift_refreshed=1")


@functools.cache
def get_dev_merged_status():
    return DevMergedStatus.from_file()


@dataclass
class DevMergedStatus:
    git_status: str
    pr_statuses: "list[PRStatus]"
    footer: str

    @staticmethod
    def from_output(output: str) -> "DevMergedStatus":
        dev_merged_pieces = output.split("\n---\n")
        return DevMergedStatus(
            git_status=dev_merged_pieces[0],
            pr_statuses=list(map(PRStatus.from_output, dev_merged_pieces[1:-1])),
            footer=dev_merged_pieces[-1],
        )

    @staticmethod
    def from_file() -> "DevMergedStatus | None":
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
    def from_output(output: str) -> "PRStatus":
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
        if self.pending_active is not None:
            d["pending_active"] = self.pending_active
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
    def from_dict(cls, d: dict) -> "TestingPR":
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

    def to_dict(self) -> dict:
        return {
            "last_deploy_at": self.last_deploy_at,
            "prs": [p.to_dict() for p in self.prs],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TestingState":
        return cls(
            last_deploy_at=d.get("last_deploy_at", ""),
            prs=[TestingPR.from_dict(p) for p in d.get("prs", [])],
        )


def _load_testing_state() -> "TestingState | None":
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


def _save_testing_state(state: TestingState) -> None:
    TESTING_STATE_FILE.write_text(json.dumps(state.to_dict(), indent=2))
    get_dev_merged_status.cache_clear()


def _is_maintainer() -> bool:
    user = get_current_user()
    return bool(user and user.is_member_of_any(["/usergroup/maintainers", "/usergroup/admin"]))


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


def _get_drift_info(state: TestingState) -> "tuple[dict, bool]":
    """Return (drift_dict, from_cache). Checks memcache first; fetches GitHub on miss.

    Keys are int PR numbers. JSON round-trip via memcache stringifies keys, so we
    re-cast on read.

    On a cache miss, also refreshes title/author/assignee on each TestingPR in-place
    and saves the state file if anything changed.
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
    if state_changed:
        _save_testing_state(state)
    mc.set(_DRIFT_CACHE_KEY, drift, expires=_DRIFT_CACHE_TTL)
    return drift, False


def _evict_drift_cache() -> None:
    cache.get_memcache().delete(_DRIFT_CACHE_KEY)


def _get_pr_info(pr_number: int) -> dict:
    """Fetch title, HEAD SHA, author, and assignee for a PR from GitHub."""
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
        }
    except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError):
        return {
            "title": f"PR #{pr_number}",
            "head_sha": "",
            "author": "",
            "author_avatar": "",
            "assignee": "",
            "assignee_avatar": "",
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
            except (urllib.error.URLError, ValueError, json.JSONDecodeError):
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
    except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError):
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


def _trigger_rebuild() -> bool:
    """Call Jenkins to trigger a rebuild. No-op if jenkins_token is not configured."""
    token = getattr(config, "jenkins_token", None)
    if not token:
        return False
    state = _load_testing_state()
    prs = state.prs if state else []
    lines = "\n".join(f"origin pull/{p.pr}/head  # {p.title}" for p in prs if p.active)
    url = f"{_JENKINS_URL}?{urlencode({'token': token, 'GH_REPO_AND_BRANCH': lines})}"
    try:
        urllib.request.urlopen(url, timeout=10)
        return True
    except (urllib.error.URLError, ValueError):
        return False


@public
def get_git_revision_short_hash():
    return status_info.get("Software version") if status_info and isinstance(status_info, dict) else None


def get_features_enabled():
    return config.features


def setup():
    "Basic startup status for the server"
    global status_info, feature_flags
    host = socket.gethostname()
    status_info = {
        "Software version": get_software_version(),
        "Python version": sys.version.split()[0],
        "Host": host,
        "Start time": datetime.datetime.now(datetime.UTC),
    }
    feature_flags = get_features_enabled()

    # Host is e.g. ol-web4.blah.archive.org ; we just want the first subdomain
    first_subdomain = host.split(".")[0] or "unknown"
    stats.increment("ol.servers.%s.started" % first_subdomain)
