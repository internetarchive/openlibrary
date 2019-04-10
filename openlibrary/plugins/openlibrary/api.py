"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)
"""

import web
import simplejson

from infogami.utils import delegate
from infogami.utils.view import render_template
from infogami.plugins.api.code import jsonapi
from openlibrary import accounts
from openlibrary.utils.isbn import isbn_10_to_isbn_13, normalize_isbn
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.plugins.worksearch.subjects import get_subject
from openlibrary.core import ia, db, models, lending, helpers as h
from openlibrary.catalog.add_book import load
from openlibrary.core.vendors import (
    get_amazon_metadata, clean_amazon_metadata_for_load,
    get_betterworldbooks_metadata)

class book_availability(delegate.page):
    path = "/availability/v2"

    def GET(self):
        i = web.input(type='', ids='')
        id_type = i.type
        ids = i.ids.split(',')
        result = self.get_book_availability(id_type, ids)
        return delegate.RawText(simplejson.dumps(result),
                                content_type="application/json")

    def POST(self):
        i = web.input(type='')
        j = simplejson.loads(web.data())
        id_type = i.type
        ids = j.get('ids', [])
        result = self.get_book_availability(id_type, ids)
        return delegate.RawText(simplejson.dumps(result),
                                content_type="application/json")

    def get_book_availability(self, id_type, ids):
        return (
            lending.get_availability_of_works(ids) if id_type == "openlibrary_work"
            else
            lending.get_availability_of_editions(ids) if id_type == "openlibrary_edition"
            else
            lending.get_availability_of_ocaids(ids) if id_type == "identifier"
            else []
        )

class ratings(delegate.page):
    path = "/works/OL(\d+)W/ratings"
    encoding = "json"

    def POST(self, work_id):
        """Registers new ratings for this work"""
        user = accounts.get_current_user()
        i = web.input(edition_id=None, rating=None, redir=False)
        key = i.edition_id if i.edition_id else ('/works/OL%sW' % work_id)
        edition_id = int(extract_numeric_id_from_olid(i.edition_id)) if i.edition_id else None

        if not user:
            raise web.seeother('/account/login?redirect=%s' % key)

        username = user.key.split('/')[2]

        def response(msg, status="success"):
            return delegate.RawText(simplejson.dumps({
                status: msg
            }), content_type="application/json")

        if i.rating is None:
            models.Ratings.remove(username, work_id)
            r = response('removed rating')

        else:
            try:
                rating = int(i.rating)
                if rating not in models.Ratings.VALID_STAR_RATINGS:
                    raise ValueError
            except ValueError:
                return response('invalid rating', status="error")

            models.Ratings.add(
                username=username, work_id=work_id,
                rating=rating, edition_id=edition_id)
            r = response('rating added')

        if i.redir:
            raise web.seeother(key)
        return r

# The GET of work_bookshelves, work_ratings, and work_likes should return some summary of likes,
# not a value tied to this logged in user. This is being used as debugging.

class work_bookshelves(delegate.page):
    path = "/works/OL(\d+)W/bookshelves"
    encoding = "json"

    def POST(self, work_id):
        user = accounts.get_current_user()
        i = web.input(edition_id=None, action="add", redir=False, bookshelf_id=None)
        key = i.edition_id if i.edition_id else ('/works/OL%sW' % work_id)

        if not user:
            raise web.seeother('/account/login?redirect=%s' % key)

        username = user.key.split('/')[2]
        current_status = models.Bookshelves.get_users_read_status_of_work(username, work_id)

        try:
            bookshelf_id = int(i.bookshelf_id)
            if bookshelf_id not in models.Bookshelves.PRESET_BOOKSHELVES.values():
                raise ValueError
        except ValueError:
            return delegate.RawText(simplejson.dumps({
                'error': 'Invalid bookshelf'
            }), content_type="application/json")

        if bookshelf_id == current_status:
            work_bookshelf = models.Bookshelves.remove(
                username=username, work_id=work_id, bookshelf_id=i.bookshelf_id)

        else:
            edition_id = int(i.edition_id.split('/')[2][2:-1]) if i.edition_id else None
            work_bookshelf = models.Bookshelves.add(
                username=username, bookshelf_id=bookshelf_id,
                work_id=work_id, edition_id=edition_id)

        if i.redir:
            raise web.seeother(key)
        return delegate.RawText(simplejson.dumps({
            'bookshelves_affected': work_bookshelf
        }), content_type="application/json")


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

class price_api(delegate.page):
    path = r'/prices'

    @jsonapi
    def GET(self):
        # @hornc, add: title='', asin='', authors=''
        i = web.input(isbn='', asin='') 

        if not (i.isbn or i.asin):
            return simplejson.dumps({
                'error': 'isbn or asin required'
            })

        id_ = i.asin if i.asin else normalize_isbn(i.isbn)
        id_type = 'asin' if i.asin else 'isbn_' + ('13' if len(id_) == 13 else '10')

        metadata = {
            'amazon': get_amazon_metadata(id_) or {},
            'betterworldbooks': get_betterworldbooks_metadata(id_) if id_type.startswith('isbn_') else {}
        }
        # if isbn_13 fails for amazon, we may want to check isbn_10 also
        # xxx

        # if bwb fails and isbn10, try again with isbn13
        if id_type == 'isbn_10' and \
           metadata['betterworldbooks'].get('price') is None:
            isbn_13 = isbn_10_to_isbn_13(id_)
            metadata['betterworldbooks'] = isbn_13 and get_betterworldbooks_metadata(
                isbn_13) or {}

        # fetch book by isbn if it exists
        # if asin... for now, it will fail (which is fine)
        matches = web.ctx.site.things({
            'type': '/type/edition',
            id_type: id_,
        })

        book_key = matches[0] if matches else None

        # if no OL edition for isbn, attempt to create
        if (not book_key) and metadata.get('amazon'):
            resp = load(clean_amazon_metadata_for_load(
                metadata.get('amazon')))
            if resp and 'edition' in resp:
                book_key = resp.get('edition').get('key')

        # include ol edition metadata in response, if available
        if book_key:
            ed = web.ctx.site.get(book_key)
            if ed:
                metadata['key'] = ed.key
                if getattr(ed, 'ocaid'):
                    metadata['ocaid'] = ed.ocaid

        return simplejson.dumps(metadata)
