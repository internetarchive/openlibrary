"""New recentchanges implementation.

This should go into infogami.
"""
import web
import simplejson
import yaml

from infogami.utils import delegate
from infogami.utils.view import public, render, render_template, add_flash_message, safeint
from infogami.utils import features

from openlibrary.utils import dateutil
from utils import get_changes


@public
def recentchanges(query):
    return web.ctx.site.recentchanges(query)
    
class index2(delegate.page):
    path = "/recentchanges"
    
    def GET(self):
        if features.is_enabled("recentchanges_v2"):
            return index().render()
        else:
            return render.recentchanges()

class index(delegate.page):
    path = "/recentchanges(/[^/0-9][^/]*)"

    def is_enabled(self):
        return features.is_enabled("recentchanges_v2")    
    
    def GET(self, kind):
        return self.render(kind=kind)
    
    def render(self, date=None, kind=None):
        query = {}
        
        if date:
            begin_date, end_date = dateutil.parse_daterange(date)
            query['begin_date'] = begin_date.isoformat()
            query['end_date'] = end_date.isoformat()
        
        if kind:
            query['kind'] = kind and kind.strip("/")

        print "encoding", web.ctx.encoding
        
        if web.ctx.encoding in ["json", "yml"]:
            return self.handle_encoding(query, web.ctx.encoding)
        
        return render_template("recentchanges/index", query)

    def handle_encoding(self, query, encoding):
        i = web.input(bot="", limit=100, offset=0, text="false")
        
        # The bot stuff is handled in the template for the regular path. 
        # We need to handle it here for api.
        if i.bot.lower() == "true":
            query['bot'] = True
        elif i.bot.lower()  == "false":
            query['bot'] = False
            
        # and limit and offset business too
        limit = safeint(i.limit, 100)
        offset = safeint(i.offset, 0)
        
        def constrain(value, low, high):
            if value < low:
                return low
            elif value > high:
                return high
            else:
                return value

        # constrain limit and offset for performance reasons
        limit = constrain(limit, 0, 1000)
        offset = constrain(offset, 0, 10000)
         
        query['limit'] = limit
        query['offset'] = offset
        
        result = [c.dict() for c in web.ctx.site.recentchanges(query)]
        
        if encoding == "json":
            response = simplejson.dumps(result)
            content_type = "application/json"
        elif encoding == "yml":
            response = self.yaml_dump(result)
            content_type = "text/x-yaml"
        else:
            response = ""
            content_type = "text/plain"
        
        if i.text.lower() == "true":
            web.header('Content-Type', 'text/plain')
        else:
            web.header('Content-Type', content_type)
        
        return delegate.RawText(response)

    def yaml_dump(self, d):
        return yaml.safe_dump(d, indent=4, allow_unicode=True, default_flow_style=False)

class index_with_date(index):
    path = "/recentchanges/(\d\d\d\d(?:/\d\d)?(?:/\d\d)?)(/[^/]*)?"
    
    def GET(self, date, kind):
        date = date.replace("/", "-")
        return self.render(kind=kind, date=date)
        
class recentchanges_redirect(delegate.page):
    path = "/recentchanges/goto/(\d+)"

    def is_enabled(self):
        return features.is_enabled("recentchanges_v2")

    def GET(self, id):
        id = int(id)
        change = web.ctx.site.get_change(id)
        if not change:
            web.ctx.status = "404 Not Found"
            return render.notfound(web.ctx.path)
    
        raise web.found(change.url())

class recentchanges_view(delegate.page):
    path = "/recentchanges/\d\d\d\d/\d\d/\d\d/[^/]*/(\d+)"
    
    def is_enabled(self):
        return features.is_enabled("recentchanges_v2")
    
    def get_change_url(self, change):
        t = change.timestamp
        return "/recentchanges/%04d/%02d/%02d/%s/%s" % (t.year, t.month, t.day, change.kind, change.id)
    
    def GET(self, id):
        id = int(id)
        change = web.ctx.site.get_change(id)
        if not change:
            web.ctx.status = "404 Not Found"
            return render.notfound(web.ctx.path)
            
        path = self.get_change_url(change)
        if path != web.ctx.path:
            raise web.redirect(path)
        else:
            tname = "recentchanges/" + change.kind + "/view"
            if tname in render:
                return render_template(tname, change)
            else:
                return render_template("recentchanges/default/view", change)
                
    def POST(self, id):
        if not features.is_enabled("undo"):
            return render_template("permission_denied", web.ctx.path, "Permission denied to undo.")
            
        id = int(id)
        change = web.ctx.site.get_change(id)
        change._undo()
        raise web.seeother(change.url())

class history(delegate.mode):
    def GET(self, path):
        page = web.ctx.site.get(path)
        if not page:
            raise web.seeother(path)
        i = web.input(page=0)
        offset = 20 * safeint(i.page)
        limit = 20
        history = get_changes(dict(key=path, limit=limit, offset=offset))
        return render.history(page, history)
