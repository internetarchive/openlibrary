"""API stuff."""
import web
import simplejson

from infogami.utils import delegate
from openlibrary.core import helpers as h

def setup():
    # placeholder
    pass

class work_editions(delegate.page):
    path = "(/works/OL\d+W)/editions"
    encoding = "json"
    
    def GET(self, key):
        doc = web.ctx.site.get(key)
        if not doc or doc.type.key != "/type/work":
            raise web.notfound('')
        else:
            i = web.input(limit=50, offset=0)
            limit = h.safeint(i.limit) or 50
            offset = h.safeint(i.offset) or 0
            
            data = self.get_editions_data(doc, limit=limit, offset=offset)
            return delegate.RawText(simplejson.dumps(data), content_type="applicaiton/json")
            
    def get_editions_data(self, work, limit, offset):
        if limit > 1000:
            limit = 1000
            
        keys = web.ctx.site.things({"type": "/type/edition", "works": work.key, "limit": limit, "offset": offset})
        editions = web.ctx.site.get_many(keys, raw=True)
        
        size = work.edition_count
        links = {
            "self": web.ctx.fullpath,
            "work": work.key,
        }
        
        if offset > 0:
            links['prev'] = web.changequery(offset=min(0, offset-limit))
            
        if offset + len(editions) < size:
            links['next'] = web.changequery(offset=offset+limit)
        
        return {
            "links": links,
            "size": size,
            "entries": editions
        }

class author_works(delegate.page):
    path = "(/authors/OL\d+A)/works"
    encoding = "json"
    
    def GET(self, key):
        doc = web.ctx.site.get(key)
        if not doc or doc.type.key != "/type/author":
            raise web.notfound('')
        else:
            i = web.input(limit=50, offset=0)
            limit = h.safeint(i.limit) or 50
            offset = h.safeint(i.offset) or 0
            
            data = self.get_works_data(doc, limit=limit, offset=offset)
            return delegate.RawText(simplejson.dumps(data), content_type="applicaiton/json")
            
    def get_works_data(self, author, limit, offset):
        if limit > 1000:
            limit = 1000
            
        keys = web.ctx.site.things({"type": "/type/work", "authors": {"author": {"key": author.key}}, "limit": limit, "offset": offset})
        works = web.ctx.site.get_many(keys, raw=True)
        
        size = author.get_work_count()
        links = {
            "self": web.ctx.fullpath,
            "author": author.key,
        }
        
        if offset > 0:
            links['prev'] = web.changequery(offset=min(0, offset-limit))
            
        if offset + len(works) < size:
            links['next'] = web.changequery(offset=offset+limit)
        
        return {
            "links": links,
            "size": size,
            "entries": works
        }