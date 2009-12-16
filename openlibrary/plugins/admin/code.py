"""Plugin to provide admin interface.
"""
import os
import web
import subprocess
import datetime

from infogami.utils import delegate
from infogami.utils.view import render, public
from infogami.utils.context import context

import openlibrary

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
        
class stats:
    def GET(self, today):
        json = web.ctx.site._conn.request(web.ctx.site.name, '/get', 'GET', {'key': '/admin/stats/' + today})
        return delegate.RawText(json)
        
    def POST(self, today):
        """Update stats for today."""
        doc = self.get_stats(today)
        doc._save()
        raise web.seeother(web.ctx.path)

    def get_stats(self, today):
        stats = web.ctx.site._request("/stats/" + today)
        
        key = '/admin/stats/' + today
        doc = web.ctx.site.new(key, {
            'key': key,
            'type': {'key': '/type/object'}
        })
        doc.edits = {
            'human': stats.edits - stats.edits_by_bots,
            'bot': stats.edits_by_bots,
            'total': stats.edits
        }
        doc.members = stats.new_accounts
        return doc
        
def daterange(date, *slice):
    return [date + datetime.timedelta(i) for i in range(*slice)]
    
def storify(d):
    if isinstance(d, dict):
        return web.storage((k, storify(v)) for k, v in d.items())
    elif isinstance(d, list):
        return [storify(v) for v in d]
    else:
        return d

def get_admin_stats():
    def f(dates):
        keys = ["/admin/stats/" + date.isoformat() for date in dates]
        docs = web.ctx.site.get_many(keys)
        return g(docs)

    def has_doc(date):
        return bool(web.ctx.site.get('/admin/stats/' + date.isoformat()))

    def g(docs):
        return {
            'edits': {
                'human': sum(doc['edits']['human'] for doc in docs),
                'bot': sum(doc['edits']['bot'] for doc in docs),
                'total': sum(doc['edits']['total'] for doc in docs),
            },
            'members': sum(doc['members'] for doc in docs)
        }
    date = datetime.datetime.utcnow().date()
    
    if has_doc(date):
        today = f([date])
    else:
        today =  g([stats().get_stats(date.isoformat())])
    yesterday = f(daterange(date, -1, 0, 1))
    thisweek = f(daterange(date, 0, -7, -1))
    thismonth = f(daterange(date, 0, -30, -1))
    
    xstats = {
        'edits': {
            'today': today['edits'],
            'yesterday': yesterday['edits'],
            'thisweek': thisweek['edits'],
            'thismonth': thismonth['edits']
        },
        'members': {
            'today': today['members'],
            'yesterday': yesterday['members'],
            'thisweek': thisweek['members'],
            'thismonth': thismonth['members'] 
        }
    }
    return storify(xstats)

def setup():
    register_admin_page('/admin/git-pull', gitpull, label='git-pull')
    register_admin_page('/admin/reload', reload, label='Reload Templates')
    register_admin_page('/admin/people', people, label='People')
    register_admin_page('/admin(/people/.*)', people_view, label='View People')
    register_admin_page('/admin/ip', ipaddress, label='IP')
    register_admin_page('/admin/ip/(.*)', ipaddress_view, label='View IP')
    register_admin_page('/admin/stats/(\d\d\d\d-\d\d-\d\d)', stats, label='Stats JSON')
    
    public(get_admin_stats)
    
class IPAddress:
    def __init__(self, ip):
        self.ip = ip

    def get_edit_history(self, limit=10, offset=0):
        return web.ctx.site.versions({"ip": self.ip, "limit": limit, "offset": offset})

setup()
