"""webtest: test utilities.
"""
import sys

# adding current directory to path to make sure local modules can be imported
sys.path.insert(0, '.')

from web.test import *
import web

class Browser(web.Browser):
    def __init__(self):
        web.Browser.__init__(self)
        if '--staging' in sys.argv:
            self.url = 'http://openlibrary.org:8080/'
        else:
            self.url = 'http://openlibrary.org/'

    def check_errors(self):
        errors = [self.get_text(e) for e in self.get_soup().findAll(attrs={'id': 'error'})]
        if errors:
            raise web.BrowserError(errors[0])

    def do_request(self, req):
        response = web.Browser.do_request(self, req)
        if self.status != 200:
            raise web.BrowserError(str(self.status))
        self.check_errors()
        return response
