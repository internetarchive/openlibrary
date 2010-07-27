"""New recentchanges implementation.

This should go into infogami.
"""
import web

from infogami.utils import delegate
from infogami.utils.view import render, render_template
from infogami.utils import features

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
            tname = "recentchanges/" + change.kind
            if tname in render:
                return render_template(tname, change)
            else:
                return render_template("recentchanges/default", change)