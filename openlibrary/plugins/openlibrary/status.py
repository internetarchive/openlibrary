import contextlib
import datetime
import functools
import json
import re
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import web

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import public, render_template
from openlibrary.accounts import get_current_user
from openlibrary.core import stats
from openlibrary.utils import get_software_version

status_info: dict[str, Any] = {}
feature_flagso: dict[str, Any] = {}

TESTING_STATE_FILE = Path('./_testing-prs.json')
_GITHUB_API_BASE = "https://api.github.com/repos/internetarchive/openlibrary"
_JENKINS_URL = "https://jenkins.openlibrary.org/job/testing-deploy/buildWithParameters"


class status(delegate.page):
    def GET(self):
        testing_prs = _load_testing_state()  # None if state file doesn't exist
        is_maintainer_user = _is_maintainer()
        drift_info = {}
        if testing_prs:
            # NOTE: makes 1-2 GitHub API calls per PR; acceptable for small testing sets
            drift_info = {p.pr: _get_pr_drift(p) for p in testing_prs}
        show_testing = testing_prs is not None or is_maintainer_user
        return render_template(
            "status",
            status_info,
            feature_flags,
            dev_merged_status=get_dev_merged_status(),
            testing_prs=testing_prs or [],
            drift_info=drift_info,
            is_maintainer=is_maintainer_user,
            show_testing=show_testing,
        )


class status_add(delegate.page):
    path = '/status/add'

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        i = web.input(pr='')
        raw = re.split(r'[\s,]+', i.pr.strip())
        pr_numbers = []
        for val in raw:
            if val:
                with contextlib.suppress(ValueError, AttributeError):
                    pr_numbers.append(_parse_pr_number(val))
        if not pr_numbers:
            raise web.badrequest()
        prs = _load_testing_state() or []
        existing = {p.pr for p in prs}
        user = get_current_user()
        for pr_number in pr_numbers:
            if pr_number not in existing:
                info = _get_pr_info(pr_number)
                prs.append(
                    TestingPR(
                        pr=pr_number,
                        commit=info['head_sha'],
                        active=True,
                        title=info['title'],
                        added_at=datetime.datetime.now(datetime.UTC).isoformat(),
                        added_by=user.key.split('/')[-1] if user else '',
                    )
                )
                existing.add(pr_number)
        _save_testing_state(prs)
        _trigger_rebuild()
        raise web.seeother('/status')


class status_remove(delegate.page):
    path = '/status/remove'

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        i = web.input(prs=[])
        to_remove = {int(p) for p in i.prs}
        _save_testing_state(
            [p for p in (_load_testing_state() or []) if p.pr not in to_remove]
        )
        _trigger_rebuild()
        raise web.seeother('/status')


class status_toggle(delegate.page):
    path = '/status/toggle'

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        i = web.input(prs=[])
        to_toggle = {int(p) for p in i.prs}
        prs = _load_testing_state() or []
        for p in prs:
            if p.pr in to_toggle:
                p.active = not p.active
        _save_testing_state(prs)
        _trigger_rebuild()
        raise web.seeother('/status')


class status_pull_latest(delegate.page):
    path = '/status/pull-latest'

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        i = web.input(prs=[])
        to_update = {int(p) for p in i.prs}
        prs = _load_testing_state() or []
        for p in prs:
            if p.pr in to_update:
                info = _get_pr_info(p.pr)
                if info['head_sha']:
                    p.commit = info['head_sha']
        _save_testing_state(prs)
        _trigger_rebuild()
        raise web.seeother('/status')


class status_rebuild(delegate.page):
    path = '/status/rebuild'

    def POST(self):
        if not _is_maintainer():
            raise web.unauthorized()
        _trigger_rebuild()
        raise web.seeother('/status')


@functools.cache
def get_dev_merged_status():
    return DevMergedStatus.from_file()


@dataclass
class DevMergedStatus:
    git_status: str
    pr_statuses: 'list[PRStatus]'
    footer: str

    @staticmethod
    def from_output(output: str) -> 'DevMergedStatus':
        dev_merged_pieces = output.split('\n---\n')
        return DevMergedStatus(
            git_status=dev_merged_pieces[0],
            pr_statuses=list(map(PRStatus.from_output, dev_merged_pieces[1:-1])),
            footer=dev_merged_pieces[-1],
        )

    @staticmethod
    def from_file() -> 'DevMergedStatus | None':
        """If we're on testing and the file exists, return staged PRs"""
        fp = Path('./_dev-merged_status.txt')
        if fp.exists() and (contents := fp.read_text()):
            return DevMergedStatus.from_output(contents)
        return None

    def get_github_search_link(self) -> str:
        """Constructs a GitHub search URL for all PRs in pr_statuses."""

        pull_ids = [pr.pull_id for pr in self.pr_statuses if pr.pull_id]

        return f"https://github.com/internetarchive/openlibrary/pulls?{urlencode({
            "q": "is:pr is:open " + " ".join([f"#{num}" for num in pull_ids])
        })}"


@dataclass
class PRStatus:
    pull_line: str
    status: str
    body: str

    @property
    def name(self) -> str | None:
        if '#' in self.pull_line:
            return self.pull_line.split(' # ')[1]
        else:
            return self.pull_line

    @property
    def pull_id(self) -> int | None:
        if m := re.match(r'^origin pull/(\d+)', self.pull_line):
            return int(m.group(1))
        else:
            return None

    @property
    def link(self) -> str | None:
        if self.pull_id is not None:
            return f'https://github.com/internetarchive/openlibrary/pull/{self.pull_id}'
        else:
            return None

    @staticmethod
    def from_output(output: str) -> 'PRStatus':
        lines = output.strip().split('\n')
        return PRStatus(pull_line=lines[0], status=lines[-1], body='\n'.join(lines[1:]))


@dataclass
class TestingPR:
    pr: int
    commit: str  # pinned commit SHA (full)
    active: bool
    title: str
    added_at: str  # ISO timestamp
    added_by: str  # OL username

    @property
    def short_commit(self) -> str:
        return self.commit[:7]

    @property
    def added_date(self) -> str:
        return self.added_at[:10] if self.added_at else ''

    def to_dict(self) -> dict:
        return {
            'pr': self.pr,
            'commit': self.commit,
            'active': self.active,
            'title': self.title,
            'added_at': self.added_at,
            'added_by': self.added_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'TestingPR':
        return cls(
            pr=d['pr'],
            commit=d['commit'],
            active=d.get('active', True),
            title=d.get('title', f"PR #{d['pr']}"),
            added_at=d.get('added_at', ''),
            added_by=d.get('added_by', ''),
        )


def _load_testing_state() -> 'list[TestingPR] | None':
    """Returns list of TestingPRs if state file exists, None otherwise."""
    if TESTING_STATE_FILE.exists():
        return [
            TestingPR.from_dict(d) for d in json.loads(TESTING_STATE_FILE.read_text())
        ]
    return None


def _save_testing_state(prs: list[TestingPR]) -> None:
    TESTING_STATE_FILE.write_text(json.dumps([p.to_dict() for p in prs], indent=2))
    get_dev_merged_status.cache_clear()


def _is_maintainer() -> bool:
    user = get_current_user()
    return bool(
        user and user.is_member_of_any(['/usergroup/maintainers', '/usergroup/admin'])
    )


def _github_get(path: str) -> dict:
    url = f"{_GITHUB_API_BASE}/{path}"
    req = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _get_pr_info(pr_number: int) -> dict:
    """Fetch title and current HEAD SHA for a PR from GitHub."""
    try:
        pr = _github_get(f"pulls/{pr_number}")
        return {
            'title': pr.get('title', f'PR #{pr_number}'),
            'head_sha': pr['head']['sha'],
        }
    except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError):
        return {'title': f'PR #{pr_number}', 'head_sha': ''}


def _get_pr_drift(pr: TestingPR) -> dict:
    """Fetch live drift info for a PR in the testing state."""
    try:
        gh = _github_get(f"pulls/{pr.pr}")
        head_sha = gh['head']['sha']
        merged = gh.get('merged') or gh.get('state') == 'closed'
        if head_sha.startswith(pr.commit) or pr.commit.startswith(head_sha[:7]):
            drift = 0
        else:
            try:
                cmp = _github_get(f"compare/{pr.short_commit}...{head_sha[:7]}")
                drift = cmp.get('ahead_by', -1)
            except (urllib.error.URLError, ValueError, json.JSONDecodeError):
                drift = -1
        return {'head_sha': head_sha[:7], 'drift': drift, 'merged': merged}
    except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError):
        return {'head_sha': '', 'drift': -1, 'merged': False}


def _parse_pr_number(value: str) -> int:
    value = value.strip()
    if m := re.search(r'/pull/(\d+)', value):
        return int(m.group(1))
    return int(value.lstrip('#'))


def _trigger_rebuild() -> bool:
    """Call Jenkins to trigger a rebuild. No-op if jenkins_token is not configured."""
    token = getattr(config, 'jenkins_token', None)
    if not token:
        return False
    prs = _load_testing_state() or []
    lines = '\n'.join(f"origin pull/{p.pr}/head  # {p.title}" for p in prs if p.active)
    url = f"{_JENKINS_URL}?{urlencode({'token': token, 'GH_REPO_AND_BRANCH': lines})}"
    try:
        urllib.request.urlopen(url, timeout=10)
        return True
    except (urllib.error.URLError, ValueError):
        return False


@public
def get_git_revision_short_hash():
    return (
        status_info.get('Software version')
        if status_info and isinstance(status_info, dict)
        else None
    )


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
    first_subdomain = host.split('.')[0] or 'unknown'
    stats.increment('ol.servers.%s.started' % first_subdomain)
