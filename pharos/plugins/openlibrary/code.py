"""
Open Library Plugin.
"""
import web
import simplejson

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
