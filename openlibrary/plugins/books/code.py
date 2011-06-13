"""Open Library Books API
"""

from infogami.plugins.api.code import add_hook
import dynlinks
import readlinks

import web
from infogami.infobase import _json as simplejson

from infogami.utils import delegate
from infogami.plugins.api.code import jsonapi

import urlparse
import re
import urllib2

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


# class read_singleget(delegate.page):
#     """Handle the single-lookup form of the Hathi-style API
#     """
#     path = r"/api/volumes/(brief|full)/(oclc|lccn|issn|isbn|htid|olid|recordnumber)/(.+)"
#     encoding = "json"
#     @jsonapi
#     def GET(self, brief_or_full, idtype, idval):
#         i = web.input()
        
#         web.ctx.headers = []
#         bibkey = '%s:%s' % (idtype, idval)
#         result = readlinks.readlink_single(bibkey, i)
#         return simplejson.dumps(result)


# class read_multiget(delegate.page):
#     """Handle the multi-lookup form of the Hathi-style API
#     """
#     path = r"/api/volumes/(brief|full)/json/(.+)"
#     path_re = re.compile(path)
#     @jsonapi
#     def GET(self, brief_or_full, bibkey_str):
#         i = web.input()

#         # Work around issue with gunicorn where semicolon and after
#         # get truncated.  (web.input() still seems ok)
#         # see https://github.com/benoitc/gunicorn/issues/215
#         raw_uri = web.ctx.env.get("RAW_URI")
#         raw_path = urlparse.urlsplit(raw_uri).path

#         # handle e.g. '%7C' for '|'
#         decoded_path = urllib2.unquote(raw_path)

#         m = self.path_re.match(decoded_path)
#         if not len(m.groups()) == 2:
#             return simplejson.dumps({})
#         (brief_or_full, bibkey_str) = m.groups()

#         web.ctx.headers = []
#         result = readlinks.readlink_multiple(bibkey_str, i)
#         return simplejson.dumps(result)


class read_singleget(delegate.page):
    """Handle the single-lookup form of the Hathi-style API
    """
    path = r"/api/volumes/(brief|full)/(oclc|lccn|issn|isbn|htid|olid|recordnumber)/(.+)"
    encoding = "json"
    @jsonapi
    def GET(self, brief_or_full, idtype, idval):
        i = web.input()

        web.ctx.headers = []
        req = '%s:%s' % (idtype, idval)
        result = readlinks.readlinks(req, i)
        if req in result:
            result = result[req]
        else:
            result = []
        return simplejson.dumps(result)


class read_multiget(delegate.page):
    """Handle the multi-lookup form of the Hathi-style API
    """
    path = r"/api/volumes/(brief|full)/json/(.+)"
    path_re = re.compile(path)
    @jsonapi
    def GET(self, brief_or_full, req): # params aren't used, see below
        i = web.input()

        # Work around issue with gunicorn where semicolon and after
        # get truncated.  (web.input() still seems ok)
        # see https://github.com/benoitc/gunicorn/issues/215
        raw_uri = web.ctx.env.get("RAW_URI")
        raw_path = urlparse.urlsplit(raw_uri).path

        # handle e.g. '%7C' for '|'
        decoded_path = urllib2.unquote(raw_path)

        m = self.path_re.match(decoded_path)
        if not len(m.groups()) == 2:
            return simplejson.dumps({})
        (brief_or_full, req) = m.groups()

        web.ctx.headers = []
        result = readlinks.readlinks(req, i)
        return simplejson.dumps(result)
