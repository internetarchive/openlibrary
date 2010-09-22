import web
import Cookie
import urllib

from infogami.utils.view import render_template
from infogami.utils import delegate
from infogami import config

from openlibrary.plugins.worksearch import code as worksearch

class MobileMiddleware:
    """WSGI middleware to delegate requests to the mobile app when the mobile
    cookie is on.
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def cookies(self, env, **defaults):
        # adopted from web.cookies
        cookie = Cookie.SimpleCookie()
        cookie.load(env.get('HTTP_COOKIE', ''))
        d = web.storify(cookie, **defaults)
        for k, v in d.items():
            d[k] = v and urllib.unquote(v)
        return d
        
    def __call__(self, environ, start_response):
        cookies = self.cookies(environ, mobile="false")
        # delegate to mobile app when cookie mobile is set to true. 
        if cookies.mobile == "true":
            return mobile_wsgi_app(environ, start_response)
        else:
            return self.wsgi_app(environ, start_response)

config.middleware.append(MobileMiddleware)
            
urls = (
    "/", "index",
    "/books/.*", "books",
    "/authors/.*", "authors",
    "/search", "search",
    "/images/.*", "static",
    
)
app = web.application(urls, globals())
# to setup ctx.site
app.add_processor(web.loadhook(delegate.initialize_context))
mobile_wsgi_app = app.wsgifunc()

def layout(page, title=None):
    return render_template("mobile/site", page, title=title)

class index:
    def GET(self):
        rc = web.ctx.site.recentchanges({"bot": True, "limit": 1000, "author": "/people/ImportBot"})
        edition_keys = []
        for change in rc:
            edition_keys.extend([c.key for c in change.changes 
                                 if c.revision == 1 and c.key.startswith("/books/")])
        editions = [ed for ed in web.ctx.site.get_many(edition_keys) if ed.ocaid]
        return layout(render_template("mobile/index", new_books=editions[:10]))

def _editions_for_works(works):
    ocaids = set()

    for work in works:
        if work.get('ia'):
            # just use the first one for now
            ocaids.add(work['ia'][0])

    edition_keys = web.ctx.site.things({"type": "/type/edition", "ocaid": list(ocaids)})
    editions = web.ctx.site.get_many(edition_keys)

    work_key_to_edition = {}
    for edition in editions:
        for work in edition.works:
            work_key_to_edition[work.key] = edition

    for work in works:
        if work.key in work_key_to_edition:
            edition = work_key_to_edition[work.key]
            yield edition, work
    

class search:
    def _do_search(self, q):
        ugly = worksearch.do_search({"q": q, "has_fulltext": "true"}, None)
        results = web.storage({'num_found': ugly['num_found'], 'books': []})
        works = [worksearch.get_doc(doc) for doc in ugly['docs']]
        for work in works:
            work.key = '/works/%s' % work.key
        for edition, work in _editions_for_works(works):
            results['books'].append((edition, work))
        return results

    def GET(self):
        i = web.input(q="")
        results = self._do_search(i.q)
        return layout(render_template("mobile/search", q=i.q, results=results))

class book:
    def GET(self, key):
        book = web.ctx.site.get(key)
        return layout(render_template("mobile/book", book=book), title=book.title)

class author:
    def GET(self, key):
        author = web.ctx.site.get(key)
        books = []
        works = author.get_books()
        works = [work for work in works['works'] if work.get('has_fulltext')]
        for edition, work in _editions_for_works(works):
            books.append((edition, work))
        
        return layout(render_template("mobile/author", author=author, books=books), title=author.title)

class static:
    def GET(self):
        raise web.seeother('/static/upstream' + web.ctx.path)
