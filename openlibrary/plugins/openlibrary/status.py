import web

import socket
import datetime
import subprocess

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template
from infogami.utils.context import context

status_info = {}

class status(delegate.page):
    def GET(self):
        return render_template("status", status_info)

def get_software_version():
    return subprocess.Popen("git rev-parse --short HEAD --".split(), stdout = subprocess.PIPE, stderr = subprocess.STDOUT).stdout.read().strip()    

def setup():
    "Basic startup status for the server"
    global status_info
    status_info = {"Software version" : get_software_version(),
                   "Host" : socket.gethostname(),
                   "Start time" : datetime.datetime.utcnow()
                   }


