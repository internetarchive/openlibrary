"""Open Library Books API
"""

import json
import re
import urllib
import web

from infogami.utils import delegate
from infogami.plugins.api.code import jsonapi

from openlibrary.plugins.books import dynlinks, readlinks


class books_json(delegate.page):
    path = "/api/books"

    @jsonapi
    def GET(self):
        i = web.input(bibkeys='', callback=None, details="false")
        if web.ctx.path.endswith('.json'):
            i.format = 'json'
        return dynlinks.dynlinks(i.bibkeys.split(","), i)


class read_singleget(delegate.page):
    """Handle the single-lookup form of the Hathi-style API"""

    path = (
        r"/api/volumes/(brief|full)/(oclc|lccn|issn|isbn|htid|olid|recordnumber)/(.+)"
    )
    encoding = "json"

    @jsonapi
    def GET(self, brief_or_full, idtype, idval):
        i = web.input()

        web.ctx.headers = []
        req = f'{idtype}:{idval}'
        result = readlinks.readlinks(req, i)
        if req in result:
            result = result[req]
        else:
            result = []
        return json.dumps(result)


class read_multiget(delegate.page):
    """Handle the multi-lookup form of the Hathi-style API"""

    path = r"/api/volumes/(brief|full)/json/(.+)"
    path_re = re.compile(path)

    @jsonapi
    def GET(self, brief_or_full, req):  # params aren't used, see below
        i = web.input()

        # Work around issue with gunicorn where semicolon and after
        # get truncated.  (web.input() still seems ok)
        # see https://github.com/benoitc/gunicorn/issues/215
        raw_uri = web.ctx.env.get("RAW_URI")
        if raw_uri:
            raw_path = urllib.parse.urlsplit(raw_uri).path

            # handle e.g. '%7C' for '|'
            decoded_path = urllib.parse.unquote(raw_path)

            m = self.path_re.match(decoded_path)
            if not len(m.groups()) == 2:
                return json.dumps({})
            (brief_or_full, req) = m.groups()

        web.ctx.headers = []
        result = readlinks.readlinks(req, i)
        return json.dumps(result)
