"""Open Library Import API
"""
 
from infogami.plugins.api.code import add_hook
from openlibrary.plugins.openlibrary.code import can_write

import web
import json

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
            
        return json.dumps({'success':False, 'error':'Not Yet Implemented'})

add_hook("import", importapi)