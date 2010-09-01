import web
from infogami.utils.view import render_template
from infogami.utils import delegate
from openlibrary.plugins.worksearch import code as worksearch

def layout(page):
    return delegate.RawText(render_template("mobile/site", page))

class index(delegate.page):
    path = "/"

    def GET(self):
        return layout(render_template("mobile/index"))

class search(delegate.page):

    def _do_search(self, q):
        ugly = worksearch.do_search({"q": q}, None)
        results = web.storage({'num_found': ugly['num_found'], 'docs': []})
        for doc in ugly['docs']:
            results['docs'].append(worksearch.get_doc(doc))
        return results

    def GET(self):
        i = web.input(q="")
        results = self._do_search(i.q)
        return layout(render_template("mobile/search", q=i.q, results=results))

class book(delegate.page):
    
    path = "(/books/.*)"

    def GET(self, key):
        book = web.ctx.site.get(key)
        return layout(render_template("mobile/book", book=book))

class author(delegate.page):

    path = "(/authors/.*)"

    def GET(self, key):
        author = web.ctx.site.get(key)
        return layout(render_template("mobile/author", author=author))
    
#class notfound(delegate.page):
#    
#    path = "/.*"
#
#    def GET(self):
#        raise web.NotFound()
