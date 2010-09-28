"""Open Library Books API
"""

from infogami.plugins.api.code import add_hook
import dynlinks

import web
from infogami.infobase import _json as simplejson

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

