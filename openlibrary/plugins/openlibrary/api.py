"""
This file should be for internal APIs which Open Library requires for
its experience. This does not include public facing APIs with LTS
(long term support)
"""

import web
import re
import json
from collections import defaultdict

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template  # noqa: F401 used for its side effects
from infogami.plugins.api.code import jsonapi
from infogami.utils.view import add_flash_message
from openlibrary import accounts
from openlibrary.plugins.openlibrary.code import can_write
from openlibrary.utils.isbn import isbn_10_to_isbn_13, normalize_isbn
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.plugins.worksearch.subjects import get_subject
from openlibrary.accounts.model import OpenLibraryAccount
from openlibrary.core import ia, db, models, lending, helpers as h
from openlibrary.core.observations import Observations, get_observation_metrics
from openlibrary.core.models import Booknotes, Work
from openlibrary.core.sponsorships import qualifies_for_sponsorship
from openlibrary.core.vendors import (
    create_edition_from_amazon_metadata,
    get_amazon_metadata,
    get_betterworldbooks_metadata,
)


class book_availability(delegate.page):
    path = "/availability/v2"

    def GET(self):
        i = web.input(type='', ids='')
        id_type = i.type
        ids = i.ids.split(',')
        result = self.get_book_availability(id_type, ids)
        return delegate.RawText(json.dumps(result), content_type="application/json")

    def POST(self):
        i = web.input(type='')
        j = json.loads(web.data())
        id_type = i.type
        ids = j.get('ids', [])
        result = self.get_book_availability(id_type, ids)
        return delegate.RawText(json.dumps(result), content_type="application/json")

    def get_book_availability(self, id_type, ids):
        return (
            lending.get_availability_of_works(ids)
            if id_type == "openlibrary_work"
            else lending.get_availability_of_editions(ids)
            if id_type == "openlibrary_edition"
            else lending.get_availability_of_ocaids(ids)
            if id_type == "identifier"
            else []
        )


class browse(delegate.page):
    path = "/browse"
    encoding = "json"

    def GET(self):
        i = web.input(
            q='', page=1, limit=100, subject='', work_id='', _type='', sorts=''
        )
        sorts = i.sorts.split(',')
        page = int(i.page)
        limit = int(i.limit)
        url = lending.compose_ia_url(
            query=i.q,
            limit=limit,
            page=page,
            subject=i.subject,
            work_id=i.work_id,
            _type=i._type,
            sorts=sorts,
        )
        works = lending.get_available(url=url) if url else []
        result = {
            'query': url,
            'works': [work.dict() for work in works],
        }
        return delegate.RawText(json.dumps(result), content_type="application/json")


class ratings(delegate.page):
    path = r"/works/OL(\d+)W/ratings"
    encoding = "json"

    @jsonapi
    def GET(self, work_id):
        from openlibrary.core.ratings import Ratings
        stats = Ratings.get_work_ratings_summary(work_id)

        if stats:
            return json.dumps({
                'summary': {
                    'average': stats['ratings_average'],
                    'count': stats['ratings_count'],
                },
                'counts': {
                    '1': stats['ratings_count_1'],
                    '2': stats['ratings_count_2'],
                    '3': stats['ratings_count_3'],
                    '4': stats['ratings_count_4'],
                    '5': stats['ratings_count_5'],
                },
            })
        else:
            return json.dumps({
                'summary': {
                    'average': None,
                    'count': 0,
                },
                'counts': {
                    '1': 0,
                    '2': 0,
                    '3': 0,
                    '4': 0,
                    '5': 0,
                },
            })


    def POST(self, work_id):
        """Registers new ratings for this work"""
        user = accounts.get_current_user()
        i = web.input(edition_id=None, rating=None, redir=False, redir_url=None, page=None, ajax=False)
        key = (i.redir_url if i.redir_url else
            i.edition_id if i.edition_id else
            ('/works/OL%sW' % work_id))
        edition_id = (
            int(extract_numeric_id_from_olid(i.edition_id)) if i.edition_id else None
        )

        if not user:
            raise web.seeother('/account/login?redirect=%s' % key)

        username = user.key.split('/')[2]

        def response(msg, status="success"):
            return delegate.RawText(
                json.dumps({status: msg}), content_type="application/json"
            )

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
                username=username, work_id=work_id, rating=rating, edition_id=edition_id
            )
            r = response('rating added')

        if i.redir and not i.ajax:
            p = h.safeint(i.page, 1)
            query_params = f'?page={p}' if p > 1 else ''
            if i.page:
                raise web.seeother(f'{key}{query_params}')

            raise web.seeother(key)
        return r


class booknotes(delegate.page):
    path = r"/works/OL(\d+)W/notes"
    encoding = "json"

    def POST(self, work_id):
        """
        Add a note to a work (or a work and an edition)
        GET params:
        - edition_id str (optional)
        - redir bool: if patron not logged in, redirect back to page after login

        :param str work_id: e.g. OL123W
        :rtype: json
        :return: the note
        """
        user = accounts.get_current_user()
        i = web.input(notes=None, edition_id=None, redir=None)
        edition_id = (
            int(extract_numeric_id_from_olid(i.edition_id)) if i.edition_id else -1
        )

        if not user:
            raise web.seeother('/account/login?redirect=/works/%s' % work_id)

        username = user.key.split('/')[2]

        def response(msg, status="success"):
            return delegate.RawText(
                json.dumps({status: msg}), content_type="application/json"
            )

        if i.notes is None:
            Booknotes.remove(username, work_id, edition_id=edition_id)
            return response('removed note')

        Booknotes.add(
            username=username, work_id=work_id, notes=i.notes, edition_id=edition_id
        )

        if i.redir:
            raise web.seeother("/works/%s" % work_id)

        return response('note added')


# The GET of work_bookshelves, work_ratings, and work_likes should return some summary of likes,
# not a value tied to this logged in user. This is being used as debugging.


class work_bookshelves(delegate.page):
    path = r"/works/OL(\d+)W/bookshelves"
    encoding = "json"

    @jsonapi
    def GET(self, work_id):
        from openlibrary.core.models import Bookshelves

        result = {'counts': {}}
        counts = Bookshelves.get_num_users_by_bookshelf_by_work_id(work_id)
        for (shelf_name, shelf_id) in Bookshelves.PRESET_BOOKSHELVES_JSON.items():
            result['counts'][shelf_name] = counts.get(shelf_id, 0)

        return json.dumps(result)

    def POST(self, work_id):
        """
        Add a work (or a work and an edition) to a bookshelf.

        GET params:
        - edition_id str (optional)
        - action str: e.g. "add", "remove"
        - redir bool: if patron not logged in, redirect back to page after login
        - bookshelf_id int: which bookshelf? e.g. the ID for "want to read"?
        - dont_remove bool: if book exists & action== "add", don't try removal

        :param str work_id: e.g. OL123W
        :rtype: json
        :return: a list of bookshelves_affected
        """
        from openlibrary.core.models import Bookshelves

        user = accounts.get_current_user()
        i = web.input(
            edition_id=None,
            action="add",
            redir=False,
            bookshelf_id=None,
            dont_remove=False,
        )
        key = i.edition_id if i.edition_id else ('/works/OL%sW' % work_id)

        if not user:
            raise web.seeother('/account/login?redirect=%s' % key)

        username = user.key.split('/')[2]
        current_status = Bookshelves.get_users_read_status_of_work(username, work_id)

        try:
            bookshelf_id = int(i.bookshelf_id)
            shelf_ids = Bookshelves.PRESET_BOOKSHELVES.values()
            if bookshelf_id != -1 and bookshelf_id not in shelf_ids:
                raise ValueError
        except (TypeError, ValueError):
            return delegate.RawText(
                json.dumps({'error': 'Invalid bookshelf'}),
                content_type="application/json",
            )

        if (not i.dont_remove) and bookshelf_id == current_status or bookshelf_id == -1:
            work_bookshelf = Bookshelves.remove(
                username=username, work_id=work_id, bookshelf_id=current_status
            )

        else:
            edition_id = int(i.edition_id.split('/')[2][2:-1]) if i.edition_id else None
            work_bookshelf = Bookshelves.add(
                username=username,
                bookshelf_id=bookshelf_id,
                work_id=work_id,
                edition_id=edition_id,
            )

        if i.redir:
            raise web.seeother(key)
        return delegate.RawText(
            json.dumps({'bookshelves_affected': work_bookshelf}),
            content_type="application/json",
        )


class work_editions(delegate.page):
    path = r"(/works/OL\d+W)/editions"
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
            return delegate.RawText(json.dumps(data), content_type="application/json")

    def get_editions_data(self, work, limit, offset):
        if limit > 1000:
            limit = 1000

        keys = web.ctx.site.things(
            {
                "type": "/type/edition",
                "works": work.key,
                "limit": limit,
                "offset": offset,
            }
        )
        editions = web.ctx.site.get_many(keys, raw=True)

        size = work.edition_count
        links = {
            "self": web.ctx.fullpath,
            "work": work.key,
        }

        if offset > 0:
            links['prev'] = web.changequery(offset=min(0, offset - limit))

        if offset + len(editions) < size:
            links['next'] = web.changequery(offset=offset + limit)

        return {"links": links, "size": size, "entries": editions}


class author_works(delegate.page):
    path = r"(/authors/OL\d+A)/works"
    encoding = "json"

    def GET(self, key):
        doc = web.ctx.site.get(key)
        if not doc or doc.type.key != "/type/author":
            raise web.notfound('')
        else:
            i = web.input(limit=50, offset=0)
            limit = h.safeint(i.limit, 50)
            offset = h.safeint(i.offset, 0)

            data = self.get_works_data(doc, limit=limit, offset=offset)
            return delegate.RawText(json.dumps(data), content_type="application/json")

    def get_works_data(self, author, limit, offset):
        if limit > 1000:
            limit = 1000

        keys = web.ctx.site.things(
            {
                "type": "/type/work",
                "authors": {"author": {"key": author.key}},
                "limit": limit,
                "offset": offset,
            }
        )
        works = web.ctx.site.get_many(keys, raw=True)

        size = author.get_work_count()
        links = {
            "self": web.ctx.fullpath,
            "author": author.key,
        }

        if offset > 0:
            links['prev'] = web.changequery(offset=min(0, offset - limit))

        if offset + len(works) < size:
            links['next'] = web.changequery(offset=offset + limit)

        return {"links": links, "size": size, "entries": works}


class sponsorship_eligibility_check(delegate.page):
    path = r'/sponsorship/eligibility/(.*)'

    @jsonapi
    def GET(self, _id):
        i = web.input(patron=None, scan_only=False)
        edition = (
            web.ctx.site.get('/books/%s' % _id)
            if re.match(r'OL[0-9]+M', _id)
            else models.Edition.from_isbn(_id)
        )
        if not edition:
            return json.dumps({"status": "error", "reason": "Invalid ISBN 13"})
        return json.dumps(
            qualifies_for_sponsorship(edition, scan_only=i.scan_only, patron=i.patron)
        )


class price_api(delegate.page):
    path = r'/prices'

    @jsonapi
    def GET(self):
        i = web.input(isbn='', asin='')
        if not (i.isbn or i.asin):
            return json.dumps({'error': 'isbn or asin required'})
        id_ = i.asin if i.asin else normalize_isbn(i.isbn)
        id_type = 'asin' if i.asin else 'isbn_' + ('13' if len(id_) == 13 else '10')

        metadata = {
            'amazon': get_amazon_metadata(id_, id_type=id_type[:4]) or {},
            'betterworldbooks': get_betterworldbooks_metadata(id_)
            if id_type.startswith('isbn_')
            else {},
        }
        # if user supplied isbn_{n} fails for amazon, we may want to check the alternate isbn

        # if bwb fails and isbn10, try again with isbn13
        if id_type == 'isbn_10' and metadata['betterworldbooks'].get('price') is None:
            isbn_13 = isbn_10_to_isbn_13(id_)
            metadata['betterworldbooks'] = (
                isbn_13 and get_betterworldbooks_metadata(isbn_13) or {}
            )

        # fetch book by isbn if it exists
        # TODO: perform existing OL lookup by ASIN if supplied, if possible
        matches = web.ctx.site.things(
            {
                'type': '/type/edition',
                id_type: id_,
            }
        )

        book_key = matches[0] if matches else None

        # if no OL edition for isbn, attempt to create
        if (not book_key) and metadata.get('amazon'):
            book_key = create_edition_from_amazon_metadata(id_, id_type[:4])

        # include ol edition metadata in response, if available
        if book_key:
            ed = web.ctx.site.get(book_key)
            if ed:
                metadata['key'] = ed.key
                if getattr(ed, 'ocaid'):
                    metadata['ocaid'] = ed.ocaid

        return json.dumps(metadata)


class patrons_observations(delegate.page):
    """
    Fetches a patron's observations for a work, requires auth, intended
    to be used internally to power the My Books Page & books pages modal
    """
    path = r"/works/OL(\d+)W/observations"
    encoding = "json"

    def GET(self, work_id):
        user = accounts.get_current_user()

        if not user:
            raise web.seeother('/account/login')

        username = user.key.split('/')[2]
        existing_records = Observations.get_patron_observations(username, work_id)

        patron_observations = defaultdict(list)

        for r in existing_records:
            kv_pair = Observations.get_key_value_pair(r['type'], r['value'])
            patron_observations[kv_pair.key].append(kv_pair.value)

        return delegate.RawText(
            json.dumps(patron_observations), content_type="application/json"
        )

    def POST(self, work_id):
        user = accounts.get_current_user()

        if not user:
            raise web.seeother('/account/login')

        data = json.loads(web.data())

        Observations.persist_observation(
            data['username'], work_id, data['observation'], data['action']
        )

        def response(msg, status="success"):
            return delegate.RawText(
                json.dumps({status: msg}), content_type="application/json"
            )

        return response('Observations added')

    def DELETE(self, work_id):
        user = accounts.get_current_user()
        username = user.key.split('/')[2]

        if not user:
            raise web.seeother('/account/login')

        Observations.remove_observations(username, work_id)

        def response(msg, status="success"):
            return delegate.RawText(
                json.dumps({status: msg}), content_type="application/json"
            )

        return response('Observations removed')


class public_observations(delegate.page):
    """
    Public observations fetches anonymized community reviews
    for a list of works. Useful for decorating search results.
    """
    path = '/observations'
    encoding = 'json'

    def GET(self):
        i = web.input(olid=[])
        works = i.olid
        metrics = {w: get_observation_metrics(w) for w in works}

        return delegate.RawText(
            json.dumps({'observations': metrics}),
            content_type='application/json'
        )


class work_delete(delegate.page):
    path = r"/works/(OL\d+W)/[^/]+/delete"

    def get_editions_of_work(self, work: Work) -> list[dict]:
        limit = 1_000  # This is the max limit of the things function
        keys: list = web.ctx.site.things(
            {"type": "/type/edition", "works": work.key, "limit": limit}
        )
        if len(keys) == limit:
            raise web.HTTPError(
                '400 Bad Request',
                data=json.dumps(
                    {
                        'error': f'API can only delete {limit} editions per work',
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
        return web.ctx.site.get_many(keys, raw=True)

    def POST(self, work_id: str):
        if not can_write():
            return web.HTTPError('403 Forbidden')

        web_input = web.input(comment=None)

        comment = web_input.get('comment')

        work: Work = web.ctx.site.get(f'/works/{work_id}')
        if work is None:
            return web.HTTPError(status='404 Not Found')

        editions: list[dict] = self.get_editions_of_work(work)
        keys_to_delete: list = [el.get('key') for el in [*editions, work.dict()]]
        delete_payload: list[dict] = [
            {'key': key, 'type': {'key': '/type/delete'}} for key in keys_to_delete
        ]

        web.ctx.site.save_many(delete_payload, comment)
        return delegate.RawText(
            json.dumps(
                {
                    'status': 'ok',
                }
            ),
            content_type="application/json",
        )
