import web

import socket
import datetime
import subprocess

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template, public

status_info = {}
feature_flags = {}

class status(delegate.page):
    def GET(self):
        template = render_template("status", status_info, feature_flags)
        template.v2 = True
        return template

@public
def get_git_revision_short_hash():
    return (status_info.get('Software version')
            if status_info and isinstance(status_info, dict) 
            else None)

def get_software_version():
    return subprocess.Popen("git rev-parse --short HEAD --".split(), stdout = subprocess.PIPE, stderr = subprocess.STDOUT).stdout.read().strip()

def get_features_enabled():
    return config.features

def setup():
    "Basic startup status for the server"
    global status_info, feature_flags
    status_info = {"Software version" : get_software_version(),
                   "Host" : socket.gethostname(),
                   "Start time" : datetime.datetime.utcnow()
                   }
    feature_flags = get_features_enabled()

