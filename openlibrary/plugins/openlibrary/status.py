import datetime
import functools
import re
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import public, render_template
from openlibrary.core import stats
from openlibrary.utils import get_software_version

status_info: dict[str, Any] = {}
feature_flagso: dict[str, Any] = {}


class status(delegate.page):
    def GET(self):
        return render_template(
            "status",
            status_info,
            feature_flags,
            dev_merged_status=get_dev_merged_status(),
        )


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
