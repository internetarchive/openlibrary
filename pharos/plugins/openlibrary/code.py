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

class addbook(delegate.page):
    def GET(self):
        page = web.ctx.site.new("", {'type': web.ctx.site.get('/type/edition')})
        return render.edit(page, '/addbook', 'Add Book')
        
    def POST(self):
        from infogami.core.code import edit
        books = web.ctx.site.things({'key~': '/b/OL*', 'sort': '-id', 'limit': 1})

        key = '/b/OL%dM' % (1 + int(web.numify(books[0])))
	web.ctx.path = key
        return edit().POST(key)

class addauthor(delegate.page):
    def POST(self):
	i = web.input("name")
	if len(i.name) < 2:
	    return web.badinput()
        authors = web.ctx.site.things({'key~': '/a/OL*', 'sort': '-id', 'limit': 1})
        key = '/a/OL%dA' % (1 + int(web.numify(authors[0])))
	web.ctx.site.write({'create': 'unless_exists', 'key': key, 'name': i.name})
	return key
        
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
        i = web.input()
        q = {'type': '/type/author', 'name~': i.prefix + '*', 'sort': 'key', 'limit': 5}
        things = web.ctx.site.things(q)
        things = [web.ctx.site.get(key) for key in things]
        
	if len(i.prefix) > 2:
	    result = [dict(type=[{'id': t.key, 'name': t.key}], name=web.utf8(t.name), guid=t.key, id=t.key, article=dict(id=t.key)) for t in things]
	else:
	    result = []
        callback = i.pop('callback')
        d = dict(status="200 OK", query=dict(i, escape='html'), code='/api/status/ok', result=result)
        print '%s(%s)' % (callback, simplejson.dumps(d))
        
class blurb(delegate.page):
    path = "/suggest/blurb/(.*)"
    def GET(self, path):
        i = web.input()        
        callback = i.pop('callback')
	author = web.ctx.site.get('/' +path)
	bio = author and author.bio or ""
        result = dict(body=web.utf8(bio), media_type="text/html", text_encoding="utf-8")
        d = dict(status="200 OK", code="/api/status/ok", result=result)
        print "%s(%s)" % (callback, simplejson.dumps(d))

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

if __name__ == "__main__":
    main()
