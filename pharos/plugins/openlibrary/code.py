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
        result = []
        for k in keys:
            if isinstance(k, dict):
                result += web.ctx.site.things(k)
            elif k.endswith('*'):
                result += web.ctx.site.things({'key~': k})
            else:
                result.append(k)
        return result
        
    def get_references(thing):
        from infogami.infobase.client import Thing
        result = []
        for key in thing.keys():
            val = thing[key]
            if isinstance(val, list):
                if val and isinstance(val[0], Thing):
                    result += [v.key for v in val]
            elif isinstance(val, Thing):
                result.append(val.key)
        return result
            
    def visit(key):
        if key in visited:
            return

        visited.add(key)

        thing = web.ctx.site.get(key)
        if not thing: 
            return

        thing._data.pop('permission', None)
        thing._data.pop('child_permission', None)
        thing._data.pop('books', None) # remove author.books back-reference
        thing._data.pop('scan_records', None) # remove editon.scan_records back-reference
        thing._data.pop('volumes', None) # remove editon.volumes back-reference
        thing._data.pop('latest_revision', None)

        for ref in get_references(thing):
            visit(ref)
            
        d = thing.dict()
        print simplejson.dumps(d)

    keys = [
        '/', 
        '/index.*', 
        '/about*', 
        '/dev*', 
        '/templates*', 
        '/macros*', 
        {'type': '/type/type'}, 
        {'type': '/type/edition', 'sort': 'created', 'limit': 1000}
    ]
    keys = expand_keys(keys)
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
        
    q1 = []
    queries = []
    
    # some hacks to break circular dependency and some work-arounds to overcome other limitations
    
    for line in f:
        q = simplejson.loads(line)
        q.pop('id', None)
        q['create'] = 'unless_exists'
        if q['type']['key'] == '/type/type':
            q1.append({'create': 'unless_exists', 'key': q['key'], 'type': q['type']})
            
            def process(v):
                if v == '\\N':
                    return None
                if isinstance(v, dict):
                    v['connect'] = 'update'
                    return v
                elif isinstance(v, list):
                    return {'connect': 'update_list', 'value': v}
                else:
                    return {'connect': 'update', 'value': v}
            for k, v in q.items():
                if k not in ['key', 'type', 'create']:
                    q[k] = process(v)
        elif q['type']['key'] == '/type/i18n_page':
            q = {'key': q['key'], 'type': q['type'], 'create': 'unless_exists'} # strip everything else
            
        queries.append(q)
    
    q = [dict(simplejson.loads(line), create='unless_exists') for line in f]
    result = web.ctx.site.write(q1 + queries)
    print result

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
        print key

class clonebook(delegate.page):
    def GET(self):
        from infogami.core.code import edit
        i = web.input("key")
        page = web.ctx.site.get(i.key)
        if page is None:
            web.seeother(i.key)
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
            print '%s(%s)' % (callback, simplejson.dumps(d))
        else:
            print simplejson.dumps(d)
        
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
            print '%s(%s)' % (callback, simplejson.dumps(d))
        else:
            print simplejson.dumps(d)

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
    print 'saving', path
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
            return web.notfound()
        else:
            title = identifier
            
            params = dict(identifier=identifier, dataserver=server, datapath=path)
            if leaf:
                params['leaf'] = leaf
            import urllib
            url = "http://%s/flipbook/flipbook.php?%s" % (server, urllib.urlencode(params))     
            print render.flipbook(url, title)

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
        print render.bookreader(id)

class robotstxt(delegate.page):
    path = "/robots.txt"
    def GET(self):
        web.header('Content-Type', 'text/plain')
        try:
            print open('static/robots.txt').read()
        except:
            return web.notfound()

class change_cover(delegate.mode):
    def GET(self, key):
        page = web.ctx.site.get(key)
        if page is None or page.type.key not in  ['/type/edition', '/type/author']:
            return web.seeother(key)
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
                return web.seeother(result[0] + ext)
            else:
                return web.notfound()
        except:
            return web.notfound()

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
