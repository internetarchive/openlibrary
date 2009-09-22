"""Plugin to provide admin interface.
"""
from infogami.utils import delegate
from infogami.utils.view import render
from infogami.utils.context import context

import openlibrary
import subprocess
import web
import os

admin_tasks = []

def register_admin_page(path, cls, label=None, visible=True):
    label = label or cls.__name__
    t = web.storage(path=path, cls=cls, label=label, visible=visible)
    admin_tasks.append(t)

class admin(delegate.page):
    path = "/admin(?:/.*)?"
    
    def delegate(self):
        if web.ctx.path == "/admin":
            return self.handle(admin_index)
            
        for t in admin_tasks:
            if t.path == web.ctx.path:
                return self.handle(t.cls)
        raise web.notfound()
        
    def handle(self, cls):
        m = getattr(cls(), web.ctx.method, None)
        if not m:
            raise web.nomethod(cls=cls)
        else:
            if self.is_admin():
                return m()
            else:
                return render.permission_denied(web.ctx.path, "Permission denied.")
        
    GET = POST = delegate
        
    def is_admin(self):
        """"Returns True if the current user is in admin usergroup."""
        return context.user and context.user.key in [m.key for m in web.ctx.site.get('/usergroup/admin').members]


class admin_index:
    def GET(self):
        return render.admin(admin_tasks)
        
class gitpull:
    def GET(self):
        root = os.path.join(os.path.dirname(openlibrary.__file__), os.path.pardir)
        root = os.path.normpath(root)
        
        p = subprocess.Popen('cd %s && git pull' % root, shell=True, stdout=subprocess.PIPE)
        out = p.stdout.read()
        p.wait()
        return '<pre>' + web.websafe(out) + '</pre>'

register_admin_page('/admin/git-pull', gitpull, label='git-pull')
