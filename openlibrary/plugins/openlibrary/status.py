import datetime
import socket
import sys
from typing import Any

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template, public
from openlibrary.core import stats
from openlibrary.utils import get_software_version

status_info: dict[str, Any] = {}
feature_flagso: dict[str, Any] = {}


class status(delegate.page):
    def GET(self):
        prs = self.get_deployed_prs()
        return render_template("status", status_info, feature_flags, staged=prs)

    def get_deployed_prs(self):
        """If we're on testing and the file exists, return staged PRs"""
        import os

        fp = '/openlibrary/_dev-merged.txt'
        if os.path.exists(fp):
            with open(fp) as r:
                return r.read()
        return ''


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
        "Start time": datetime.datetime.utcnow(),
    }
    feature_flags = get_features_enabled()

    # Host is e.g. ol-web4.blah.archive.org ; we just want the first subdomain
    first_subdomain = host.split('.')[0] or 'unknown'
    stats.increment('ol.servers.%s.started' % first_subdomain)
