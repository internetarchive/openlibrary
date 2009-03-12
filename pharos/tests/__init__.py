"""
Open Library Test Suite using functest.

Usage:

    $ functest tests
"""

import sys, os
dir = os.path.abspath(os.path.dirname(__file__) + "/..")
sys.path.append(dir)

import web
import ol, run
import infogami
from infogami.infobase import server
from infogami.utils.delegate import app

ol.app = app

# overwrite _cleanup to stop clearing thread state between requests
ol.app._cleanup = lambda *a: None

def setup_module(module):
    setup_ol()
    monkey_patch_browser()
    module.t = ol.db.transaction()

def teardown_module(module):
    module.t.rollback()

def setup_ol():
    infogami.config.db_printing = False

    infogami.config.db_parameters = web.config.db_parameters = ol.config.db_parameters
    ol.config.infobase_server = None
    web.load()

    server._infobase = ol.get_infobase()
    ol.db = server._infobase.store.db
    ol.db.printing = False

    infogami._setup()

def monkey_patch_browser():
    def check_errors(self):
        errors = [self.get_text(e) for e in 
            self.get_soup().findAll(attrs={'id': 'error'}) +
            self.get_soup().findAll(attrs={'class': 'wrong'})]
        if errors:
            raise web.BrowserError(errors[0])

    _do_request = web.AppBrowser.do_request

    def do_request(self, req):
        response = _do_request(self, req)
        if self.status != 200:
            raise web.BrowserError(str(self.status))
        self.check_errors()
        return response

    web.AppBrowser.do_request = do_request
    web.AppBrowser.check_errors = check_errors

