"""Plugin to provide admin interface.
"""
import os
import sys
import web
import subprocess
import datetime
import urllib, urllib2
import traceback
import logging

import couchdb
import yaml

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render, public
from infogami.utils.context import context

from infogami.utils.view import add_flash_message
import openlibrary
from openlibrary.core import admin as admin_stats
from openlibrary.plugins.upstream.account import as_admin
from openlibrary.plugins.upstream import forms

import services
import support

logger = logging.getLogger("openlibrary.admin")

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
        """Returns True if the current user is in admin usergroup."""
        return context.user and context.user.key in [m.key for m in web.ctx.site.get('/usergroup/admin').members]

class admin_index:
    def GET(self):
        return render_template("admin/index",get_counts())
        
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
        servers = config.get("plugin_admin", {}).get("webservers", [])
        if servers:
            body = "".join(self.reload(servers))
        else:
            body = "No webservers specified in the configuration file."
        
        return render_template("message", "Reload", body)
        
    def reload(self, servers):
        for s in servers:
            s = web.rstrips(s, "/") + "/_reload"
            yield "<h3>" + s + "</h3>"
            try:
                response = urllib.urlopen(s).read()
                print s, response
                yield "<p><pre>" + response[:100] + "</pre></p>"
            except:
                yield "<p><pre>%s</pre></p>" % traceback.format_exc()
        
@web.memoize
def local_ip():
    import socket
    return socket.gethostbyname(socket.gethostname())

class _reload(delegate.page):
    def GET(self):
        # make sure the request is coming from the LAN.
        if web.ctx.ip not in ['127.0.0.1', '0.0.0.0'] and web.ctx.ip.rsplit(".", 1)[0] != local_ip().rsplit(".", 1)[0]:
            return render.permission_denied(web.ctx.fullpath, "Permission denied to reload templates/macros.")
        
        from infogami.plugins.wikitemplates import code as wikitemplates
        wikitemplates.load_all()

        from openlibrary.plugins.upstream import code as upstream
        upstream.reload()
        return delegate.RawText("done")

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
            
    def POST(self, key):
        user = web.ctx.site.get(key)
        if not user:
            raise web.notfound()
            
        i = web.input(action=None)
        if i.action == "update_email":
            return self.POST_update_email(user, i)
        elif i.action == "update_password":
            return self.POST_update_password(user, i)
    
    def POST_update_email(self, user, i):
        @as_admin
        def f():
            web.ctx.site.update_user_details(user.get_username(), email=i.email)
            
        if not forms.vemail.valid(i.email):
            return render_template("admin/people/view", user, i, {"email": forms.vemail.msg})

        if not forms.email_not_already_used.valid(i.email):
            return render_template("admin/people/view", user, i, {"email": forms.email_not_already_used.msg})
            
        f()
        add_flash_message("info", "Email updated successfully!")
        raise web.seeother(web.ctx.path)
    
    def POST_update_password(self, user, i):
        @as_admin
        def f():
            # Infobase API doesn't provide any easier way to reset password. It must be fixed.
            site = web.ctx.site
            email = user.get_email()
            code = site.get_reset_code(email)['code']
            site.reset_password(username=user.get_username(), code=code, password=i.password)
            
        if not forms.vpass.valid(i.password):
            return render_template("admin/people/view", user, i, {"password": forms.vpass.msg})
            
        f()
        logger.info("updated password of %s", user.key)
        add_flash_message("info", "Password updated successfully!")
        raise web.seeother(web.ctx.path)
        
class ipaddress:
    def GET(self):
        return render_template('admin/ip/index')
        
class ipaddress_view:
    def GET(self, ip):
        return render_template('admin/ip/view', ip)

    def POST(self, ip):
        i = web.input(changesets=[], comment="Revert", action="revert")
        if i.action == "block":
            self.block(ip)
        else:
            self.revert(i.changesets, i.comment)
        raise web.redirect(web.ctx.path)

    def block(self, ip):
        ips = get_blocked_ips()
        if ip not in ips:
            ips.append(ip)
        block().block_ips(ips)

    def get_doc(self, key, revision):
        if revision == 0:
            return {
                "key": key,
                "type": {"key": "/type/delete"}
            }
        else:
            return web.ctx.site.get(key, revision).dict()

    def revert(self, changeset_ids, comment):
        logger.debug("Reverting changesets %s", changeset_ids)
        site = web.ctx.site
        docs = [self.get_doc(c['key'], c['revision']-1) 
                for cid in changeset_ids 
                for c in site.get_change(cid).changes]

        logger.debug("Reverting %d docs", len(docs))
        data = {
            "reverted_changesets": [str(cid) for cid in changeset_ids]
        }
        return web.ctx.site.save_many(docs, action="revert", data=data, comment=comment)

        
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

class ipstats:
    def GET(self):
        web.header('Content-Type', 'application/json')
        json = urllib.urlopen("http://www.archive.org/download/stats/numUniqueIPsOL.json").read()
        return delegate.RawText(json)
        
class block:
    def GET(self):
        page = web.ctx.site.get("/admin/block") or web.storage(ips=[web.storage(ip="127.0.0.1", duration="1 week", since="1 day")])
        return render_template("admin/block", page)
    
    def POST(self):
        i = web.input()
        ips = [ip.strip() for ip in i.ips.splitlines()]
        self.block_ips(ips)
        add_flash_message("info", "Saved!")
        raise web.seeother("/admin/block")
        
    def block_ips(self, ips):
        page = web.ctx.get("/admin/block") or web.ctx.site.new("/admin/block", {"key": "/admin/block", "type": "/type/object"})
        page.ips = [{'ip': ip} for ip in ips]
        page._save("updated blocked IPs")

def get_blocked_ips():
    doc = web.ctx.site.get("/admin/block")
    if doc:
        return [d.ip for d in doc.ips]
    else:
        return []

def block_ip_processor(handler):
    if not web.ctx.path.startswith("/admin") \
        and (web.ctx.method == "POST" or web.ctx.path.endswith("/edit")) \
        and web.ctx.ip in get_blocked_ips():
        
        return render_template("permission_denied", web.ctx.path, "Your IP address is blocked.")
    else:
        return handler()
        
def daterange(date, *slice):
    return [date + datetime.timedelta(i) for i in range(*slice)]
    
def storify(d):
    if isinstance(d, dict):
        return web.storage((k, storify(v)) for k, v in d.items())
    elif isinstance(d, list):
        return [storify(v) for v in d]
    else:
        return d

def get_counts():
    """Generate counts for various operations which will be given to the
    index page"""
    retval = admin_stats.get_stats(100)
    return storify(retval)

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
    
from openlibrary.plugins.upstream import borrow
class loans_admin:
    
    def GET(self):
        loans = borrow.get_all_loans()

        # Preload books
        web.ctx.site.get_many([loan['book'] for loan in loans])

        return render_template("admin/loans", loans, None)
        
    def POST(self):
        i = web.input(action=None)
        
        # Sanitize
        action = None
        actions = ['updateall']
        if i.action in actions:
            action = i.action
            
        if action == 'updateall':
            borrow.update_all_loan_status()
        raise web.seeother(web.ctx.path) # Redirect to avoid form re-post on re-load

class service_status(object):
    def GET(self):
        try:
            f = open("%s/olsystem.yml"%config.admin.olsystem_root)
            nodes = services.load_all(yaml.load(f), config.admin.nagios_url)
            f.close()
        except IOError, i:
            f = None
            nodes = []
        return render_template("admin/services", nodes)

class inspect:
    def GET(self, section):
        if section == "store":
            return self.GET_store()
        else:
            raise web.notfound()
        
    def GET_store(self):
        i = web.input(key=None, type=None, name=None, value=None)
        
        if i.key:
            doc = web.ctx.site.store.get(i.key)
            if doc:
                docs = [doc]
            else:
                docs = []
        else:
            docs = web.ctx.site.store.values(type=i.type or None, name=i.name or None, value=i.value or None, limit=100)
            
        return render_template("admin/inspect/store", docs, input=i)

def setup():
    register_admin_page('/admin/git-pull', gitpull, label='git-pull')
    register_admin_page('/admin/reload', reload, label='Reload Templates')
    register_admin_page('/admin/people', people, label='People')
    register_admin_page('/admin(/people/.*)', people_view, label='View People')
    register_admin_page('/admin/ip', ipaddress, label='IP')
    register_admin_page('/admin/ip/(.*)', ipaddress_view, label='View IP')
    register_admin_page('/admin/stats/(\d\d\d\d-\d\d-\d\d)', stats, label='Stats JSON')
    register_admin_page('/admin/ipstats', ipstats, label='IP Stats JSON')
    register_admin_page('/admin/block', block, label='')
    register_admin_page('/admin/loans', loans_admin, label='')
    register_admin_page('/admin/status', service_status, label = "Open Library services")
    register_admin_page('/admin/support', support.cases, label = "Support cases")
    register_admin_page('/admin/support/case/(case-\d+)', support.case, label = "Support cases")
    register_admin_page('/admin/inspect(?:/(.+))?', inspect, label="")

    support.setup()
    import mem

    for p in [mem._memory, mem._memory_type, mem._memory_id]:
        register_admin_page('/admin' + p.path, p)

    public(get_admin_stats)
    public(get_blocked_ips)
    delegate.app.add_processor(block_ip_processor)
    
setup()
