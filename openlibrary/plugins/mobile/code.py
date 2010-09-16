import web
from infogami.utils.view import render_template
from infogami.utils import delegate
from openlibrary.plugins.worksearch import code as worksearch

def layout(page, title=None):
    return delegate.RawText(render_template("mobile/site", page, title=title))

class index(delegate.page):
    path = "/"

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
    

class search(delegate.page):

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

class book(delegate.page):
    
    path = r"(/books/.*)"

    def GET(self, key):
        book = web.ctx.site.get(key)
        return layout(render_template("mobile/book", book=book), title=book.title)

class author(delegate.page):

    path = "(/authors/.*)"

    def GET(self, key):
        author = web.ctx.site.get(key)
        books = []
        works = author.get_books()
        works = [work for work in works['works'] if work.get('has_fulltext')]
        for edition, work in _editions_for_works(works):
            books.append((edition, work))
        
        return layout(render_template("mobile/author", author=author, books=books), title=author.title)
