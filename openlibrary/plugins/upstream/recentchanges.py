"""New recentchanges implementation.

This should go into infogami.
"""
import web

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
        
        return render_template("recentchanges/index", query)

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
        print "## history"
        for h in history:
            print h.__dict__
        return render.history(page, history)
