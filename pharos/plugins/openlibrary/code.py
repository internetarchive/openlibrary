"""
Open Library Plugin.
"""
import web
import simplejson

from infogami.utils import types, delegate
from infogami.utils.view import render

types.register_type('^/a/[^/]*$', '/type/author')
types.register_type('^/b/[^/]*$', '/type/edition')

class addbook(delegate.page):
    def GET(self):
        page = web.ctx.site.new("", {'type': '/type/edition'})
        return render.edit(page)
        
    def POST(self):
        from infogami.core.code import edit
        books = web.ctx.site.things(dict(type='/type/edition', sort='-id', limit=1))
        key = books[0]
        return edit().POST(key, action='/addbook', title='Add Book')
        
class clonebook(delegate.page):
    def GET(self):
        i = web.input("key")
        page = web.ctx.site.get(i.key)
        if page is None:
            web.seeother(i.key)
        else:
            page.isbn_10 = 10
            return edit().POST(key, action='/addbook', title='Clone Book')

class search(delegate.page):
    path = "/suggest/search"
    
    def GET(self):
        i = web.input()
        q = {'type': '/type/author', 'name~': i.prefix + '*', 'order': 'key', 'limit': 5}
        things = web.ctx.site.things(q)
        things = [web.ctx.site.get(key) for key in things]
        
        d  = dict(type=[{'id': '/type/author', 'name': 'Author'}])
        result = [dict(d, name=str(t.title), guid=t.key, id=t.key, article=dict(id=t.key)) for t in things]
        callback = i.pop('callback')
        d = dict(status="200 OK", query=dict(i, escape='html'), code='/api/status/ok', result=result)
        print '%s(%s)' % (callback, simplejson.dumps(d))
        
class blurb(delegate.page):
    path = "/suggest/blurb/(.*)"
    def GET(self, path):
        i = web.input()        
        callback = i.pop('callback')
        result = dict(body="hello, world!", media_type="text/html", text_encoding="utf-8")
        d = dict(status="200 OK", code="/api/status/ok", result=result)
        print "%s(%s)" % (callback, simplejson.dumps(d))

class thumbnail(delegate.page):
    path = "/suggest/thumbnail"
