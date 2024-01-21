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
    """
    Endpoint for mapping bib keys (e.g. ISBN, LCCN) to certain links associated
    with Open Library editions, such as the thumbnail URL.

    - `bibkeys` is expected a comma separated string of ISBNs, LCCNs, etc.
    - `import_missing=1` will attempt to import an edition from a supplied ISBN
      if no matching edition is found.

    Example call:
        http://localhost:8080/api/books.json?bibkeys=059035342X,0312368615&import_missing=1

    Returns a JSONified dictionary of the form:
        {"059035342X": {
            "bib_key": "059035342X",
            "info_url": "http://localhost:8080/books/OL43M/Harry_Potter_and_the_Sorcerer's_Stone",
            "preview": "noview",
            "preview_url": "https://archive.org/details/lccn_078073006991",
            "thumbnail_url": "https://covers.openlibrary.org/b/id/21-S.jpg"
            }
        "0312368615": {...}
        }
    """

    path = "/api/books"

    @jsonapi
    def GET(self):
        i = web.input(bibkeys='', callback=None, details="false", import_missing=0)
        if web.ctx.path.endswith('.json'):
            i.format = 'json'
            i.import_missing = int(i.import_missing)
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
        result = result.get(req, [])
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
        if raw_uri := web.ctx.env.get("RAW_URI"):
            raw_path = urllib.parse.urlsplit(raw_uri).path

            # handle e.g. '%7C' for '|'
            decoded_path = urllib.parse.unquote(raw_path)

            m = self.path_re.match(decoded_path)
            if len(m.groups()) != 2:
                return json.dumps({})
            (brief_or_full, req) = m.groups()

        web.ctx.headers = []
        result = readlinks.readlinks(req, i)
        return json.dumps(result)
