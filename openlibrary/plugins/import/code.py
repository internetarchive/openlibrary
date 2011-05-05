"""Open Library Import API
"""
 
from infogami.plugins.api.code import add_hook
from openlibrary.plugins.openlibrary.code import can_write
from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.parse import read_edition

import web
import json

def parse_meta_headers(edition):
    # parse S3-style http headers
    # we don't yet support augmenting complex fields like author or language
    string_keys = ['title', 'title_prefix', 'description']

    prefix = 'HTTP_X_ARCHIVE_META_'

    for k, v in web.ctx.env.items():
        if k.startswith(prefix):
            meta_key = k[len(prefix):].lower()
            if meta_key in string_keys:
                edition[meta_key] = v

class importapi:
    def GET(self):
        i = web.input(recipient='', callback=None, details="false")
 
        web.ctx.headers = []
        if i.get("format") == "json":
            web.header('Content-Type', 'application/json')
        else:
            web.header('Content-Type', 'text/javascript')
 
        if len(i.recipient) == 0:
            i.recipient = 'world'
 
        return '"hello %s"' % i.recipient

    def POST(self):
        web.header('Content-Type', 'application/json')

        if not can_write():
            return json.dumps({'success':False, 'error':'Permission Denied'})

        data = web.data()
        rec = MarcBinary(data)
        edition = read_edition(rec)

        parse_meta_headers(edition)

        return json.dumps({'success':False, 'error':'Not Yet Implemented'})

add_hook("import", importapi)
