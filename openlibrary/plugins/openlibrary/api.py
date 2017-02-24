
"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)
"""

import web
import simplejson

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core import ia, lending, helpers as h
from openlibrary.data import popular


popular_editions = popular.popular


class popular_books(delegate.page):
    path = '/popular'

    def GET(self, start=0, limit=100):
        """Returns `limit` popular book tuples of form [ocaid, olid] starting
        at `start`

        Popular books may be requested in pages of up to 100.

        TODO: Add memcached caching (see plugins/openlibrary/home.py)
        """
        i = web.input(start=start, limit=limit)
        start, limit = int(i.start), int(i.limit),
        books = popular_editions[start : start + limit]
        result = {
            'books': books,
            'limit': limit,
            'start': start,
            'next': start + limit
        } if books else {'error': 'out_of_range'}
        return delegate.RawText(simplejson.dumps(result),
                                content_type="application/json")

def format_edition(edition):
    """This should be moved to a books or carousel model"""
    collections = ia.get_meta_xml(edition.get('ocaid')).get("collection", [])
    book = {
        'ocaid': edition.get('ocaid'),
        'title': edition.title or None,
        'key': edition.key,
        'url': edition.url(),
        'authors': [web.storage(key=a.key, name=a.name or None)
                    for a in edition.get_authors()],
        'collections': collections,
        'protected': any([c in collections for c in
                          ['lendinglibrary', 'browserlending', 'inlibrary']])
    }

    cover = edition.get_cover()
    if cover:
        book['cover_url'] = cover.url(u'M')

    if 'printdisabled' in collections or 'lendinglibrary' in collections:
        book['daisy_url'] = edition.url("/daisy")
    if 'lendinglibrary' in collections:
        book['borrow_url'] = edition.url("/borrow")
    elif 'inlibrary' in collections:
        book['inlibrary_borrow_url'] = edition.url("/borrow")
    else:
        book['read_url'] = "//archive.org/stream/" + book['ocaid']
    return book

class get_editions(delegate.page):
    path = '/api/editions'

    def GET(self, max_limit=100):
        i = web.input(olids='', decoration=None, pixel=None)
        keys = i.olids.split(',')

        if i.decoration == "carousel_item":
            decorate = lambda book: render_template(
                'books/carousel_item', web.storage(book), pixel=i.pixel).__body__
        else:
            decorate = lambda book: book  # identity

        if len(keys) > max_limit:
            result = {'error': 'max_limit_%s' % max_limit}
        else:
            result = {
                'books': []
            }
            for edition in web.ctx.site.get_many(keys):
                try:
                    result['books'].append(decorate(format_edition(edition)))
                except:
                    pass
        return delegate.RawText(simplejson.dumps(result),
                                content_type="application/json")

class editions_availability(delegate.page):
    path = "/availability"

    def POST(self):
        i = simplejson.loads(web.data())
        ocaids = i.get('ocaids', [])
        j = web.input(acs='1', restricted='0')
        acs, restricted = bool(int(j.acs)), bool(int(j.restricted))
        result = lending.is_borrowable(ocaids, acs=acs, restricted=restricted)
        return delegate.RawText(simplejson.dumps(result),
                                content_type="application/json")

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
            return delegate.RawText(simplejson.dumps(data), content_type="application/json")

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
            return delegate.RawText(simplejson.dumps(data), content_type="application/json")

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
