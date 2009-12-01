"""Plugin to provide admin interface.
"""
from infogami.utils import delegate
from infogami.utils.view import render
from infogami.utils.context import context

import openlibrary
import subprocess
import web
import os


def render_template(name, *a, **kw):
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return render[name](*a, **kw)

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
            m = web.re_compile('^' + t.path + '$').match(web.ctx.path)
            if m:
                return self.handle(t.cls, m.groups())
        raise web.notfound()
        
    def handle(self, cls, args=()):
        m = getattr(cls(), web.ctx.method, None)
        if not m:
            raise web.nomethod(cls=cls)
        else:
            if self.is_admin():
                return m(*args)
            else:
                return render.permission_denied(web.ctx.path, "Permission denied.")
        
    GET = POST = delegate
        
    def is_admin(self):
        """"Returns True if the current user is in admin usergroup."""
        return context.user and context.user.key in [m.key for m in web.ctx.site.get('/usergroup/admin').members]


class admin_index:
    def GET(self):
        return render_template("admin/index")
        
class gitpull:
    def GET(self):
        root = os.path.join(os.path.dirname(openlibrary.__file__), os.path.pardir)
        root = os.path.normpath(root)
        
        p = subprocess.Popen('cd %s && git pull' % root, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = p.stdout.read()
        p.wait()
        return '<pre>' + web.websafe(out) + '</pre>'

class reload:
    def GET(self):
        from infogami.plugins.wikitemplates import code
        code.load_all()
        return delegate.RawText('done')
        
class any:
    def GET(self):
        path = web.ctx.path

class people:
    def GET(self):
        return render_template("admin/people/index")

class people_view:
    def GET(self, key):
        user = web.ctx.site.get(key)
        if user:
            return render_template('admin/people/view', user)
        else:
            raise web.notfound()
            
class ipaddress:
    def GET(self):
        return render_template('admin/ip/index')
        
class ipaddress_view:
    def GET(self, ip):
        ip = IPAddress(ip)
        return render_template('admin/ip/view', ip)

def setup():
    register_admin_page('/admin/git-pull', gitpull, label='git-pull')
    register_admin_page('/admin/reload', reload, label='Reload Templates')
    register_admin_page('/admin/people', people, label='People')
    register_admin_page('/admin(/people/.*)', people_view, label='View People')
    register_admin_page('/admin/ip', ipaddress, label='IP')
    register_admin_page('/admin/ip/(.*)', ipaddress_view, label='View IP')
    
class IPAddress:
    def __init__(self, ip):
        self.ip = ip

    def get_edit_history(self, limit=10, offset=0):
        return web.ctx.site.versions({"ip": self.ip, "limit": limit, "offset": offset})

setup()