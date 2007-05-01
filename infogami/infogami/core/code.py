import web
from infogami import utils
from infogami.utils import delegate
from infogami.utils.macro import macro
from diff import better_diff
import db
import auth
import forms

render = utils.view.render.core

def notfound():
    web.ctx.status = '404 Not Found'
    return render.special.do404()

def deleted():
    web.ctx.status = '404 Not Found'
    return render.special.deleted()

class view (delegate.mode):
    def GET(self, site, path):
        try:
            p = db.get_version(site, path, web.input(v=None).v)
        except db.NotFound:
            return notfound()
        else:
            if p.type.name == 'delete':
                return deleted()
            else:
                return render.view(p)
        
class edit (delegate.mode):
    def GET(self, site, path):
        i = web.input(v=None, t=None)
        
        if i.t:
            type = db.get_type(i.t) or db.new_type(i.t)
        else:
            type = db.get_type('page')
            
        try:
            p = db.get_version(site, path, i.v)
            if i.t:
                p.type = type
        except db.NotFound:
            schema = db.get_schema(site, type)
            schema.pop('*', None)
            data = web.storage()
            for k in schema:
                if k != '*':
                    if k.endswith('*'):
                        data[k] = ['']
                    else:
                        data[k] = ''
            p = db.new_version(site, path, type, data)

        return render.edit(p)
    
    def dict_subset(self, d, keys):
        return dict([(k, v) for k, v in d.iteritems() if k in keys])
        
    def input(self, site):
        i = web.input(_type="page", _method='post')
        
        if '_save' in i: 
            action = 'save'
        elif '_preview' in i: 
            action = 'preview'
        elif '_delete' in i: 
            action = 'delete'
        else:
            action = None
        
        type = db.get_type(i._type, create=True)
        schema = db.get_schema(site, type)
        plurals = dict([(k, []) for k,v in schema.items() if v.endswith('*')])
        i = web.input(_method='post', **plurals)
        if '*' in schema:
            d = [(k, v) for k, v in i.iteritems() if not k.startswith('_')]
            i = dict(d)
        else:
            d = [(k, i[k]) for k in schema]
            i = dict(d)
        return action, type, i
    
    def POST(self, site, path):
        action, type, data = self.input(site)
        p = db.new_version(site, path,type, data)
        
        if action == 'preview':
            return render.edit(p, preview=True)
        elif action == 'save':
            author = auth.get_user()
            try:
                p.save(author=author, ip=web.ctx.ip)
                delegate.run_hooks('on_new_version', site, path, p)
                return web.seeother(web.changequery(m=None))
            except db.ValidationException, e:
                utils.view.set_error(str(e))
                return render.edit(p)
        elif action == 'delete':
            p.type = db.get_type('delete', create=True)
            p.save()
            return web.seeother(web.changequery(m=None))
            
class history (delegate.mode):
    def GET(self, site, path):
        try:
            p = db.get_version(site, path)
            return render.history(p)
        except db.NotFound:
            return web.seeother('/' + path)
            
@macro
def PageList(path):
    from infogami.utils.context import context 
    pages = db.list_pages(context.site, path)
    for p in pages:
        yield "* [%s](/%s)" % (p.name, p.name)
    
class diff (delegate.mode):
    def GET(self, site, path):  
        i = web.input("b", a=None)
        i.a = i.a or int(i.b)-1

        try:
            a = db.get_version(site, path, revision=i.a)
            b = db.get_version(site, path, revision=i.b)
        except:
            return web.badrequest()

        alines = a.body.splitlines()
        blines = b.body.splitlines()
        
        map = better_diff(alines, blines)
        return render.diff(map, a, b)

class random(delegate.page):
    def GET(self, site):
        p = db.get_random_page(site)
        return web.seeother(p.path)

#@@ pagelist can be a macro now.
#class pagelist(delegate.page):
#    def GET(self, site):
#        d = db.get_all_pages(site)
#        return render.pagelist(d)

class recentchanges(delegate.page):
    def GET(self, site):
        d = db.get_recent_changes(site)
        return render.recentchanges(web.ctx.homepath, d)
    
class login(delegate.page):
    def GET(self, site):
        return render.login(forms.login())

    def POST(self, site):
        i = web.input(remember=False, redirect='/')
        user = db.login(i.username, i.password)
        if user is None:
            f = forms.login()
            f.fill(i)
            f.note = 'Invalid username or password.'
            return render.login(f)

        auth.setcookie(user, i.remember)
        web.seeother(web.ctx.homepath + i.redirect)
        
class register(delegate.page):
    def GET(self, site):
        return render.register(forms.register())
        
    def POST(self, site):
        i = web.input(remember=False, redirect='/')
        f = forms.register()
        if not f.validates(i):
            return render.register(f)
        else:
            user = db.new_user(i.username, i.email, i.password)
            user.save()
            auth.setcookie(user, i.remember)
            web.seeother(web.ctx.homepath + i.redirect)

class logout(delegate.page):
    def POST(self, site):
        web.setcookie("infogami_session", "", expires=-1)
        web.seeother(web.ctx.homepath + '/')

class login_reminder(delegate.page):
    def GET(self, site):
        print "Not yet implemented."

_preferences = {}
def register_preferences(name, handler):
    _preferences[name] = handler

class preferences(delegate.page):
    @auth.require_login    
    def GET(self, site):
        d = dict((name, p.GET(site)) for name, p in _preferences.iteritems())
        return render.preferences(d.values())

    @auth.require_login    
    def POST(self, site):
        i = web.input("_action")
        result = _preferences[i._action].POST(site)
        d = dict((name, p.GET(site)) for name, p in _preferences.iteritems())
        if result:
            d[i._action] = result
        return render.preferences(d.values())

class login_preferences:
    def GET(self, site):
        f = forms.login_preferences()
        return render.login_preferences(f)
        
    def POST(self, site):
        i = web.input("email", "password", "password2")
        f = forms.login_preferences()
        if not f.validates(i):
            return render.login_preferences(f)
        else:
            user = auth.get_user()
            user.password = i.password
            user.save()
            return self.GET(site)

register_preferences("login_preferences", login_preferences())

class sitepreferences(delegate.page):
    def GET(self, site):
        perms = db.get_site_permissions(site)
        return render.sitepreferences(perms)
        
    def POST(self, site):
        perms = self.input()
        db.set_site_permissions(site, perms)
        return render.sitepreferences(perms)
    
    def input(self):
        i = web.input()
        re_who = web.re_compile("who(\d+)_path\d+")
        re_what = web.re_compile("what(\d+)_path\d+")
        paths = [(k, v) for k, v in i.iteritems() if k.startswith('path')]
        values = []
        for key, path in sorted(paths):
            path = path.strip()
            if path == "":
                continue
                
            who_keys = [re_who.sub(r'\1', k) for k in i
                            if k.endswith(key) and k.startswith('who')]            
            what_keys = [re_what.sub(r'\1', k) for k in i
                            if k.endswith(key) and k.startswith('what')]
            x = sorted(who_keys)
            y = sorted(what_keys)
            assert x == y
            whos = [i["who%s_%s" % (k, key)].strip() for k in x]
            whats = [i["what%s_%s" % (k, key)].strip() for k in x]
            
            perms = [(a, b) for a, b in zip(whos, whats) if a != ""]
            values.append((path, perms))
            
        return values
        
def has_permission(site, user, path, mode):
    """Tests whether user has permision to do `mode` on site/path.
    """
    path = '/' + path
    perms = db.get_site_permissions(site)
        
    def get_items():
        import re
        for pattern, items in perms:
            if re.match('^' + pattern + '$', path):
                return items

    def has_perm(who, what):
        if mode in what:
            return (who == 'everyone') \
                or (user is not None and who in (user.name, 'loggedin-users'))
        else: 
            return False
    
    def any(seq):
        for x in seq:
            if x: 
                return True
        return False
        
    items = get_items() or []        
    return any(has_perm(who, what) for who, what in items)