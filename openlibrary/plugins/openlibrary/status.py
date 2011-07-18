import web

import socket
import datetime

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template
from infogami.utils.context import context

status_info = {}

class status(delegate.page):
    def GET(self):
        return render_template("status", status_info)


def setup():
    "Basic startup status for the server"
    global status_info
    from openlibrary import version
    status_info = dict (version = version.version,
                        host = socket.gethostname(),
                        starttime = datetime.datetime.utcnow())


