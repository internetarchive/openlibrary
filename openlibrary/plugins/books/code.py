"""Open Library Books API
"""

from infogami.plugins.api.code import add_hook
import dynlinks
import readlinks

import web
from infogami.infobase import _json as simplejson

from infogami.utils import delegate
from infogami.plugins.api.code import jsonapi


class books:
    def GET(self):
        i = web.input(bibkeys='', callback=None, details="false")
        
        web.ctx.headers = []
        if i.get("format") == "json":
            web.header('Content-Type', 'application/json')
        else:
            web.header('Content-Type', 'text/javascript')
        
        return dynlinks.dynlinks(i.bibkeys.split(","), i)
        
add_hook("books", books)


class read_singleget(delegate.page):
    """Handle the single-lookup form of the Hathi-style API
    """
    path = r"/api/volumes/(brief|full)/(oclc|lccn|issn|isbn|htid|olid|recordnumber)/(.+)"
    encoding = "json"
    @jsonapi
    def GET(self, brief_or_full, idtype, idval):
        i = web.input()
        
        web.ctx.headers = []
        bibkey = '%s:%s' % (idtype, idval)
        result = readlinks.readlink_single(bibkey, i)
        return simplejson.dumps(result)


class read_multiget(delegate.page):
    """Handle the multi-lookup form of the Hathi-style API
    """
    path = r"/api/volumes/(brief|full)/json/(.+)"
    @jsonapi
    def GET(self, brief_or_full, bibkey_str):
        i = web.input()

        web.ctx.headers = []
        result = readlinks.readlink_multiple(bibkey_str, i)
        return simplejson.dumps(result)
