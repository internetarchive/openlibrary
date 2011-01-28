"""
Open Library Plugin.
"""
import web
import simplejson
import os
import urllib
import socket
import datetime
from time import time

import infogami

# make sure infogami.config.features is set
if not hasattr(infogami.config, 'features'):
    infogami.config.features = []
    
from infogami.utils import delegate
from infogami.utils.view import render, public, safeint, add_flash_message
from infogami.infobase import client
from infogami.core.db import ValidationException

from openlibrary.utils.isbn import isbn_13_to_isbn_10

import processors

delegate.app.add_processor(processors.ReadableUrlProcessor())
delegate.app.add_processor(processors.ProfileProcessor())

def setup_invalidation_processor():
    from openlibrary.core.processors.invalidation import InvalidationProcessor
    
    config = infogami.config.get("invalidation", {})

    prefixes = config.get('prefixes', [])
    timeout = config.get("timeout", 60)
    cookie_name = config.get("cookie", "invalidation_timestamp")
    
    if prefixes:
        p = InvalidationProcessor(prefixes, timeout=timeout, cookie_name=cookie_name)
        delegate.app.add_processor(p)
        client.hooks.append(p.hook)

setup_invalidation_processor()


try:
    from infogami.plugins.api import code as api
except:
    api = None

# http header extension for OL API
infogami.config.http_ext_header_uri = "http://openlibrary.org/dev/docs/api"

# setup special connection with caching support
import connection
client._connection_types['ol'] = connection.OLConnection
infogami.config.infobase_parameters = dict(type="ol")

# set up infobase schema. required when running in standalone mode.
from openlibrary.core import schema
schema.register_schema()

if infogami.config.get('infobase_server') is None:
    # setup infobase hooks for OL
    from openlibrary.plugins import ol_infobase
    ol_infobase.init_plugin()

from openlibrary.core import models
models.register_models()
models.register_types()


# this adds /show-marc/xxx page to infogami
import showmarc

# add zip and tuple to the list of public functions
public(zip)
public(tuple)
public(isbn_13_to_isbn_10)
public(time)
public(web.input)
public(simplejson.dumps)
web.template.Template.globals['NEWLINE'] = "\n"

# Remove movefiles install hook. openlibrary manages its own files.
infogami._install_hooks = [h for h in infogami._install_hooks if h.__name__ != "movefiles"]

import lists
lists.setup()

class hooks(client.hook):
    def before_new_version(self, page):
        if page.key.startswith('/a/') or page.key.startswith('/authors/'):
            if page.type.key == '/type/author':
                return
                
            books = web.ctx.site.things({"type": "/type/edition", "authors": page.key})
            books = books or web.ctx.site.things({"type": "/type/work", "authors": {"author": {"key": page.key}}})
            if page.type.key == '/type/delete' and books:
                raise ValidationException("Deleting author pages is not allowed.")
            elif page.type.key != '/type/author' and books:
                raise ValidationException("Changing type of author pages is not allowed.")

@infogami.action
def sampledump():
    """Creates a dump of objects from OL database for creating a sample database."""
    def expand_keys(keys):
        def f(k):
            if isinstance(k, dict):
                return web.ctx.site.things(k)
            elif k.endswith('*'):
                return web.ctx.site.things({'key~': k})
            else:
                return [k]
        result = []
        for k in keys:
            d = f(k)
            result += d
        return result
        
    def get_references(data, result=None):
        if result is None:
            result = []
            
        if isinstance(data, dict):
            if 'key' in data:
                result.append(data['key'])
            else:
                get_references(data.values(), result)
        elif isinstance(data, list):
            for v in data:
                get_references(v, result)
        return result
        
    visiting = {}
    visited = set()
    
    def visit(key):
        if key in visited or key.startswith('/type/'):
            return
        elif key in visiting:
            # This is a case of circular-dependency. Add a stub object to break it.
            print simplejson.dumps({'key': key, 'type': visiting[key]['type']})
            visited.add(key)
            return
        
        thing = web.ctx.site.get(key)
        if not thing:
            return

        d = thing.dict()
        d.pop('permission', None)
        d.pop('child_permission', None)
        d.pop('table_of_contents', None)
        
        visiting[key] = d
        for ref in get_references(d.values()):
            visit(ref)
        visited.add(key)
        
        print simplejson.dumps(d)

    keys = [
        '/scan_record',
        '/scanning_center',
        {'type': '/type/scan_record', 'limit': 10},
    ]
    keys = expand_keys(keys) + ['/b/OL%dM' % i for i in range(1, 100)]
    visited = set()

    for k in keys:
        visit(k)
    
@infogami.action
def sampleload(filename="sampledump.txt.gz"):
    if filename.endswith('.gz'):
        import gzip
        f = gzip.open(filename)
    else:
        f = open(filename)
    
    queries = [simplejson.loads(line) for  line in f]
    print web.ctx.site.save_many(queries)

class addbook(delegate.page):
    path = "/addbook"
    
    def GET(self):
        d = {'type': web.ctx.site.get('/type/edition')}

        i = web.input()
        author = i.get('author') and web.ctx.site.get(i.author)
        if author:
            d['authors'] = [author]
        
        page = web.ctx.site.new("", d)
        return render.edit(page, self.path, 'Add Book')
        
    def POST(self):
        from infogami.core.code import edit
        key = web.ctx.site.new_key('/type/edition')
        web.ctx.path = key
        return edit().POST(key)

class addauthor(delegate.page):
    path = '/addauthor'
        
    def POST(self):
        i = web.input("name")
        if len(i.name) < 2:
            return web.badrequest()
        key = web.ctx.site.new_key('/type/author')
        web.ctx.path = key
        web.ctx.site.save({'key': key, 'name': i.name, 'type': dict(key='/type/author')}, comment='New Author')
        raise web.HTTPError("200 OK", {}, key)

class clonebook(delegate.page):
    def GET(self):
        from infogami.core.code import edit
        i = web.input("key")
        page = web.ctx.site.get(i.key)
        if page is None:
            raise web.seeother(i.key)
        else:
            d =page._getdata()
            for k in ['isbn_10', 'isbn_13', 'lccn', "oclc"]:
                 d.pop(k, None)
            return render.edit(page, '/addbook', 'Clone Book')

class search(delegate.page):
    path = "/suggest/search"
    
    def GET(self):
        i = web.input(prefix="")
        if len(i.prefix) > 2:
            q = {'type': '/type/author', 'name~': i.prefix + '*', 'sort': 'name', 'limit': 5}
            things = web.ctx.site.things(q)
            things = [web.ctx.site.get(key) for key in things]
        
            result = [dict(type=[{'id': t.key, 'name': t.key}], name=web.utf8(t.name), guid=t.key, id=t.key, article=dict(id=t.key)) for t in things]
        else:
            result = []
        callback = i.pop('callback', None)
        d = dict(status="200 OK", query=dict(i, escape='html'), code='/api/status/ok', result=result)

        if callback:
            data = '%s(%s)' % (callback, simplejson.dumps(d))
        else:
            data = simplejson.dumps(d)
        raise web.HTTPError('200 OK', {}, data)
        
class blurb(delegate.page):
    path = "/suggest/blurb/(.*)"
    def GET(self, path):
        i = web.input()        
        callback = i.pop('callback', None)
        author = web.ctx.site.get('/' +path)
        body = ''
        if author.birth_date or author.death_date:
            body = "%s - %s" % (author.birth_date, author.death_date)
        else:
            body = "%s" % author.date

        body += "<br/>"
        if author.bio:
            body += web.utf8(author.bio)

        result = dict(body=body, media_type="text/html", text_encoding="utf-8")
        d = dict(status="200 OK", code="/api/status/ok", result=result)
        if callback:
            data = '%s(%s)' % (callback, simplejson.dumps(d))
        else:
            data = simplejson.dumps(d)

        raise web.HTTPError('200 OK', {}, data)

class thumbnail(delegate.page):
    path = "/suggest/thumbnail"

@public
def get_property_type(type, name):
    for p in type.properties:
        if p.name == name:
            return p.expected_type
    return web.ctx.site.get("/type/string")

def save(filename, text):
    root = os.path.dirname(__file__)
    path = root + filename
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)
    f = open(path, 'w')
    f.write(text)
    f.close()

def change_ext(filename, ext):
    filename, _ = os.path.splitext(filename)
    if ext:
        filename = filename + ext
    return filename

def get_pages(type, processor):
    pages = web.ctx.site.things(dict(type=type))
    for p in pages:
        processor(web.ctx.site.get(p))

class flipbook(delegate.page):
    path = "/details/([a-zA-Z0-9_-]*)(?:/leaf(\d+))?"

    SCRIPT_PATH = "/petabox/sw/bin/find_item.php"

    def GET(self, identifier, leaf):
        if leaf:
            hash = '#page/n%s' % leaf
        else:
            hash = ""
        
        url = "http://www.archive.org/stream/%s%s" % (identifier, hash)
        raise web.seeother(url)

class bookreader(delegate.page):
    path = "/bookreader/(.*)"

    def GET(self, id):
        data = render.bookreader(id)
        raise web.HTTPError("200 OK", {}, data)

class robotstxt(delegate.page):
    path = "/robots.txt"
    def GET(self):
        web.header('Content-Type', 'text/plain')
        try:
            data = open('static/robots.txt').read()
            raise web.HTTPError("200 OK", {}, data)
        except IOError:
            raise web.notfound()
            
class change_cover(delegate.mode):
    def GET(self, key):
        page = web.ctx.site.get(key)
        if page is None or page.type.key not in  ['/type/edition', '/type/author']:
            raise web.seeother(key)
        return render.change_cover(page)
        
class bookpage(delegate.page):
    path = r"/(isbn|oclc|lccn|ia|ISBN|OCLC|LCCN|IA)/([^./]*)(/.*)?"

    def GET(self, key, value, suffix):
        key = key.lower()
        suffix = suffix or ""
        
        print (key, value, suffix)
        
        if key == "isbn":
            if len(value) == 13:
                key = "isbn_13"
            else:
                key = "isbn_10"
        elif key == "oclc":
            key = "oclc_numbers"
        elif key == "ia":
            key = "ocaid"

        if key != 'ocaid': # example: MN41558ucmf_6
            value = value.replace('_', ' ')

        if web.ctx.encoding and web.ctx.path.endswith("." + web.ctx.encoding): 
            ext = "." + web.ctx.encoding
        else:
            ext = ""
        
        if web.ctx.env.get('QUERY_STRING'):
            ext += '?' + web.ctx.env['QUERY_STRING']
            
        def redirect(key, ext, suffix):
            if ext:
                return web.found(key + ext)
            else:
                book = web.ctx.site.get(key)
                return web.found(book.url(suffix))

        q = {"type": "/type/edition", key: value}
        try:
            result = web.ctx.site.things(q)
            if result:
                raise redirect(result[0], ext, suffix)
            elif key =='ocaid':
                q = {"type": "/type/edition", 'source_records': 'ia:' + value}
                result = web.ctx.site.things(q)
                if result:
                    raise redirect(result[0], ext, suffix)
                q = {"type": "/type/volume", 'ia_id': value}
                result = web.ctx.site.things(q)
                if result:
                    raise redirect(redirect[0], ext, suffix)
            web.ctx.status = "404 Not Found"
            return render.notfound(web.ctx.path, create=False)
        except web.HTTPError:
            raise
        except:
            web.ctx.status = "404 Not Found"
            return render.notfound(web.ctx.path, create=False)

delegate.media_types['application/rdf+xml'] = 'rdf'
class rdf(delegate.mode):
    name = 'view'
    encoding = 'rdf'

    def GET(self, key):
        page = web.ctx.site.get(key)
        if not page:
            raise web.notfound("")
        else:
            from infogami.utils import template
            try:
                result = template.typetemplate('rdf')(page)
            except:
                raise web.notfound("")
            else:
                return delegate.RawText(result, content_type="application/rdf+xml; charset=utf-8")

delegate.media_types['application/marcxml+xml'] = 'marcxml'
class marcxml(delegate.mode):
    name = 'view'
    encoding = 'marcxml'
    
    def GET(self, key):
        page = web.ctx.site.get(key)
        
        if page is None or page.type.key != '/type/edition':
            raise web.notfound("")
        else:
            from infogami.utils import template
            try:
                result = template.typetemplate('marcxml')(page)
            except:
                raise web.notfound("")
            else:
                return delegate.RawText(result, content_type="application/marcxml+xml; charset=utf-8")

delegate.media_types['text/x-yaml'] = 'yml'
class _yaml(delegate.mode):
    name = "view"
    encoding = "yml"

    def GET(self, key):
        d = self.get_data(key)
        
        if web.input(text="false").text.lower() == "true":
            web.header('Content-Type', 'text/plain')
        else:
            web.header('Content-Type', 'text/x-yaml')
            
        raise web.ok(self.dump(d))
        
    def get_data(self, key):
        i = web.input(v=None)
        v = safeint(i.v, None)
        data = dict(key=key, revision=v)
        try:
            d = api.request('/get', data=data)
        except client.ClientException, e:
            if e.json:
                msg = self.dump(simplejson.loads(e.json))
            else:
                msg = e.message
            raise web.HTTPError(e.status, data=msg)
    
        return simplejson.loads(d)
        
    def dump(self, d):
        import yaml
        return yaml.safe_dump(d, indent=4, allow_unicode=True, default_flow_style=False)
        
    def load(self, data):
        import yaml
        return yaml.safe_load(data)

class _yaml_edit(_yaml):
    name = "edit"
    encoding = "yml"
    
    def is_admin(self):
        u = delegate.context.user
        return u and u.is_admin()
    
    def GET(self, key):
        # only allow admin users to edit yaml
        if not self.is_admin():
            return render.permission_denied(key, 'Permission Denied')
            
        try:
            d = self.get_data(key)
        except web.HTTPError, e:
            if web.ctx.status.lower() == "404 not found":
                d = {"key": key}
            else:
                raise
        return render.edit_yaml(key, self.dump(d))
        
    def POST(self, key):
        # only allow admin users to edit yaml
        if not self.is_admin():
            return render.permission_denied(key, 'Permission Denied')
            
        i = web.input(body='', _comment=None)
        
        if '_save' in i:
            d = self.load(i.body)
            p = web.ctx.site.new(key, d)
            try:
                p._save(i._comment)
            except (client.ClientException, ValidationException), e:            
                add_flash_message('error', str(e))
                return render.edit_yaml(key, i.body)                
            raise web.seeother(key + '.yml')
        elif '_preview' in i:
            add_flash_message('Preview not supported')
            return render.edit_yaml(key, i.body)
        else:
            add_flash_message('unknown action')
            return render.edit_yaml(key, i.body)        

def can_write():
    user = delegate.context.user and delegate.context.user.key
    usergroup = web.ctx.site.get('/usergroup/api')
    return usergroup and user in [u.key for u in usergroup.members]

class Forbidden(web.HTTPError):
    def __init__(self, msg=""):
        web.HTTPError.__init__(self, "403 Forbidden", {}, msg)

class BadRequest(web.HTTPError):
    def __init__(self, msg=""):
        web.HTTPError.__init__(self, "400 Bad Request", {}, msg)

class new:
    """API to create new author/edition/work/publisher/series.
    """
    def prepare_query(self, query):
        """Add key to query and returns the key.
        If query is a list multiple queries are returned.
        """
        if isinstance(query, list):
            return [self.prepare_query(q) for q in query]
        else:
            type = query['type']
            if isinstance(type, dict):
                type = type['key']
            query['key'] = web.ctx.site.new_key(type)
            return query['key']
            
    def verify_types(self, query):
        if isinstance(query, list):
            for q in query:
                self.verify_types(q)
        else:
            if 'type' not in query:
                raise BadRequest("Missing type")
            type = query['type']
            if isinstance(type, dict):
                if 'key' not in type:
                    raise BadRequest("Bad Type: " + simplejson.dumps(type))
                type = type['key']
                
            if type not in ['/type/author', '/type/edition', '/type/work', '/type/series', '/type/publisher']:
                raise BadRequest("Bad Type: " + simplejson.dumps(type))
 
    def POST(self):
        if not can_write():
            raise Forbidden("Permission Denied.")
            
        try:
            query = simplejson.loads(web.data())
            h = api.get_custom_headers()
            comment = h.get('comment')
            action = h.get('action')
        except Exception, e:
            raise BadRequest(str(e))
            
        self.verify_types(query)
        keys = self.prepare_query(query)
        
        try:
            if not isinstance(query, list):
                query = [query]
            web.ctx.site.save_many(query, comment=comment, action=action)
        except client.ClientException, e:
            raise BadRequest(str(e))
        return simplejson.dumps(keys)
        
api and api.add_hook('new', new)

@public
def changequery(query=None, **kw):
    if query is None:
        query = web.input(_method='get', _unicode=False)
    for k, v in kw.iteritems():
        if v is None:
            query.pop(k, None)
        else:
            query[k] = v

    query = dict((k, (map(web.safestr, v) if isinstance(v, list) else web.safestr(v))) for k, v in query.items())
    out = web.ctx.get('readable_path', web.ctx.path)
    if query:
        out += '?' + urllib.urlencode(query, doseq=True)
    return out

# Hack to limit recent changes offset.
# Large offsets are blowing up the database.

from infogami.core.db import get_recent_changes as _get_recentchanges
@public
def get_recent_changes(*a, **kw):
    if 'offset' in kw and kw['offset'] > 5000:
        return []
    else:
        return _get_recentchanges(*a, **kw)

@public
def most_recent_change():
    if 'cache_most_recent' in infogami.config.features:
        v = web.ctx.site._request('/most_recent')
        v.thing = web.ctx.site.get(v.key)
        v.author = v.author and web.ctx.site.get(v.author)
        v.created = client.parse_datetime(v.created)
        return v
    else:
        return get_recent_changes(limit=1)[0]
    
def wget(url):
    try:
        return urllib.urlopen(url).read()
    except:
        return ""
    
@public
def get_cover_id(key):
    try:
        _, cat, oln = key.split('/')
        return simplejson.loads(wget('http://covers.openlibrary.org/%s/query?olid=%s&limit=1' % (cat, oln)))[0]
    except (ValueError, IndexError, TypeError):
        return None

local_ip = None
class invalidate(delegate.page):
    path = "/system/invalidate"
    def POST(self):
        global local_ip
        if local_ip is None:
            local_ip = socket.gethostbyname(socket.gethostname())

        if web.ctx.ip != "127.0.0.1" and web.ctx.ip.rsplit(".", 1)[0] != local_ip.rsplit(".", 1)[0]:
            raise Forbidden("Allowed only in the local network.")

        data = simplejson.loads(web.data())
        if not isinstance(data, list):
            data = [data]
        for d in data:
            thing = client.Thing(web.ctx.site, d['key'], client.storify(d))
            client._run_hooks('on_new_version', thing)
        return delegate.RawText("ok")
            
def save_error():
    t = datetime.datetime.utcnow()
    name = '%04d-%02d-%02d/%02d%02d%02d%06d' % (t.year, t.month, t.day, t.hour, t.minute, t.second, t.microsecond)
    
    path = infogami.config.get('errorlog', 'errors') + '/'+ name + '.html'
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)
    
    error = web.safestr(web.djangoerror())
    f = open(path, 'w')
    f.write(error)
    f.close()
    
    print >> web.debug, 'error saved to', path
    
    return name

def internalerror():
    i = web.input(_method='GET', debug='false')
    name = save_error()
    
    if i.debug.lower() == 'true':
        raise web.debugerror()
    else:
        msg = render.site(render.internalerror(name))
        raise web.internalerror(web.safestr(msg))
    
delegate.app.internalerror = internalerror
delegate.add_exception_hook(save_error)

class memory(delegate.page):
    path = "/debug/memory"

    def GET(self):
        import guppy
        h = guppy.hpy()
        return delegate.RawText(str(h.heap()))

class backdoor(delegate.page):
    path = "/debug/backdoor"
    
    def GET(self):
        import backdoor
        reload(backdoor)
        result = backdoor.inspect()
        if isinstance(result, basestring):
            result = delegate.RawText(result)
        return result
        
# monkey-patch to check for lowercase usernames on register
from infogami.core.forms import register
username_validator = web.form.Validator("Username already used", lambda username: not web.ctx.site._request("/has_user", data={"username": username}))
register.username.validators = list(register.username.validators) + [username_validator]

def setup():
    import home
    home.setup()
    
setup()