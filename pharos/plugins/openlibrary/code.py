"""
Open Library Plugin.
"""
import web
import simplejson
import os

import infogami
from infogami.utils import types, delegate
from infogami.utils.view import render, public

types.register_type('^/a/[^/]*$', '/type/author')
types.register_type('^/b/[^/]*$', '/type/edition')

# this adds /show-marc/xxx page to infogami
import showmarc

# add zip and tuple to the list of public functions
public(zip)
public(tuple)
web.template.Template.globals['NEWLINE'] = "\n"

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
        if key in visited:
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
        
        visiting[key] = d
        for ref in get_references(d.values()):
            visit(ref)
        visited.add(key)
        
        print simplejson.dumps(d)

    keys = [
        '/', 
        '/recentchanges',
        '/index.*', 
        '/about*', 
        '/dev*', 
        {'type': '/type/template', 'key~': '/templates*'},
        {'type': '/type/macro', 'key~': '/macros*'},
        {'type': '/type/type'}, 
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
    def GET(self):
        d = {'type': web.ctx.site.get('/type/edition')}

        i = web.input()
        author = i.get('author') and web.ctx.site.get(i.author)
        if author:
            d['authors'] = [author]
        
        page = web.ctx.site.new("", d)
        return render.edit(page, '/addbook', 'Add Book')
        
    def POST(self):
        from infogami.core.code import edit
        key = web.ctx.site.new_key('/type/edition')
        web.ctx.path = key
        return edit().POST(key)

class addauthor(delegate.page):
    def POST(self):
        i = web.input("name")
        if len(i.name) < 2:
            return web.badrequest()
        key = web.ctx.site.new_key('/type/author')
        web.ctx.path = key
        web.ctx.site.write({'create': 'unless_exists', 'key': key, 'name': i.name, 'type': dict(key='/type/author')}, comment='New Author')
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

def get_templates():
    get_pages('/type/template', lambda page: save(change_ext(page.key,'.html'), page.body))

def get_macros():
    get_pages('/type/macro', lambda page: save(change_ext(page.key, '.html'), page.macro))

def get_i18n():
    from infogami.plugins.i18n.code import unstringify
    def process(page):
        text = "\n".join("%s = %s" % (k, repr(v)) for k, v in unstringify(page.dict()).items())
        save(page.key, text)
    get_pages('/type/i18n', process)

@infogami.action
def pull_templates():
    """Pull templates, macros and i18n strings to checkin them repository."""
    get_templates()
    get_macros()
    get_i18n()

class flipbook(delegate.page):
    path = "/details/([a-zA-Z0-9_-]*)(?:/leaf(\d+))?"

    SCRIPT_PATH = "/petabox/sw/bin/find_item.php"

    def GET(self, identifier, leaf):
        import os

        if os.path.exists(self.SCRIPT_PATH):
            server, path = self.find_location(identifier)
        else:
            server, path = self.find_location_from_archive(identifier)

        if  not server:
            raise web.notfound()
        else:
            title = identifier
            
            params = dict(identifier=identifier, dataserver=server, datapath=path)
            if leaf:
                params['leaf'] = leaf
            import urllib
            url = "http://%s/flipbook/flipbook.php?%s" % (server, urllib.urlencode(params))     
            data = render.flipbook(url, title)
            raise web.HTTPError("200 OK", {}, web.safestr(data))

    def find_location_from_archive(self, identifier):
        """Use archive.org to get the location.
        """
        import urllib, re
        from xml.dom import minidom

        base_url = "http://www.archive.org/services/find_file.php?loconly=1&file="

        try:
            data= urllib.urlopen(base_url + identifier).read()
            doc = minidom.parseString(data)
            vals = [(e.getAttribute('host'), e.getAttribute('dir')) for e in doc.getElementsByTagName('location')]
            return vals and vals[0]
        except Exception:
            return None, None
            
    def find_location(self, identifier):
        import os
        data = os.popen(self.SCRIPT_PATH + ' ' + identifier).read().strip()
        if ':' in data:
            return data.split(':', 1)
        else:
            return None, None

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
    path = r"/(isbn|oclc|lccn|ISBN|OCLC|LCCN)/([^.]*)(\.rdf|\.json|)"

    def GET(self, key, value, ext=None):
        key = key.lower()
        if key == "isbn":
            if len(value) == 13:
                key = "isbn_13"
            else:
                key = "isbn_10"
        elif key == "oclc":
            key = "oclc_numbers"

        value = value.replace('_', ' ')

        q = {"type": "/type/edition", key: value}
        try:
            result = web.ctx.site.things(q)
            if result:
                raise web.seeother(result[0] + ext)
            else:
                raise web.notfound()
        except:
            raise web.notfound()

class rdf(delegate.page):
    path = r"(.*)\.rdf"

    def GET(self, key):
        page = web.ctx.site.get(key)
        if not page:
            raise web.notfound()
        else:
            from infogami.utils import template

            try:
                result = template.typetemplate('rdf')(page)
            except:
                raise web.notfound()
            raise web.HTTPError("200 OK", {}, result)

class create:
    """API hook for creating books and authors."""
    def POST(self):
        ip = web.ctx.ip
        assert ip in ['127.0.0.1', '207.241.226.140']
        pass
        
def assert_localhost(ip):
    import socket
    local_ip = socket.gethostbyname(socket.gethostname())
    localhost = '127.0.0.1'
    assert ip in [localhost, local_ip]
    
class new:
    """API Hook to support book import.
    Key the new object being created is automatically computed based on the type.
    Works only from the localhost.    
    """
    def POST(self):
        assert_localhost(web.ctx.ip)
        i = web.input("query", comment=None, machine_comment=None)
        query = simplejson.loads(i.query)
        
        if isinstance(query['type'], dict):
            type = query['type']['key']
        else:
            type = query['type']
        
        
        if type == '/type/edition' or type == '/type/author':
            query['key'] = web.ctx.site.new_key(type)
        else:
            result = {'status': 'fail', 'message': 'Invalid type %s. Expected /type/edition or /type/author.' % repr(query['type'])}
            return simplejson.dumps(result)
        result = web.ctx.site._conn.request(web.ctx.site.name, '/write', 'POST',
            dict(query=simplejson.dumps(query), comment=i.comment, machine_comment=i.machine_comment))
        return simplejson.dumps(result)

class write:
    """Hack to support push and pull of templates.
    Works only from the localhost.
    """
    def POST(self):
        assert_localhost(web.ctx.ip)
        
        i = web.input("query", comment=None)
        query = simplejson.loads(i.query)
        result = web.ctx.site.write(query, i.comment)
        return simplejson.dumps(dict(status='ok', result=dict(result)))

# add search API if api plugin is enabled.
if 'api' in delegate.get_plugins():
    from infogami.plugins.api import code as api
    api.add_hook('write', write)
    api.add_hook('new', new)

if __name__ == "__main__":
    main()
