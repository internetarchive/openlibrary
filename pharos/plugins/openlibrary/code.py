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

class addbook(delegate.page):
    def GET(self):
        page = web.ctx.site.new("", {'type': web.ctx.site.get('/type/edition')})
        return render.edit(page, '/addbook', 'Add Book')
        
    def POST(self):
        from infogami.core.code import edit
        #books = web.ctx.site.things({'key~': '/b/OL*', 'sort': '-id', 'limit': 1})

        # sorry for the mess, but this is the quickest fix for Bug#
        #books = web.query("select key from thing where site_id=1 and key LIKE '/b/OL%%M' order by cast(ltrim(rtrim(key, 'M'), '/b/OL') as int) desc limit 1")
        books = web.query("select key from thing where site_id=1 and key like '/b/OL%%M' and type=52 order by id desc limit 1")

        b = books[0].key
        key = '/b/OL%dM' % (1 + int(web.numify(b)))
        web.ctx.path = key
        return edit().POST(key)

class addauthor(delegate.page):
    def POST(self):
        i = web.input("name")
        if len(i.name) < 2:
            return web.badrequest()
        #authors = web.ctx.site.things({'key~': '/a/OL*', 'sort': '-id', 'limit': 1})
        #authors = web.query("select key from thing where site_id=1 and key LIKE '/a/OL%%' and created < order by cast(ltrim(rtrim(key, 'A'), '/a/OL') as int) desc limit 1")
        authors = web.query("select key from thing where site_id=1 and key like '/a/OL%%A' and type=58 order by id desc limit 1")
        a = authors[0].key
        key = '/a/OL%dA' % (1 + int(web.numify(a)))
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
        bio = author and author.bio or ""
        result = dict(body=web.utf8(bio), media_type="text/html", text_encoding="utf-8")
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

class bookreader(delegate.page):
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
            print render.bookreader(url, title)

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

class robotstxt(delegate.page):
    path = "/robots.txt"
    def GET(self):
        web.header('Content-Type', 'text/plain')
        try:
            print open('static/robots.txt').read()
        except:
            return web.notfound()
    
if __name__ == "__main__":
    main()
