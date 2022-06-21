"""Controller for /borrow page.
"""

import web

import datetime
import json

import eventer

from infogami.plugins.api.code import jsonapi
from infogami.utils import delegate
from infogami.utils.view import render_template  # noqa: F401 used for its side effects

from openlibrary.core import helpers as h
from openlibrary.core import statsdb
from openlibrary.plugins.worksearch.subjects import SubjectEngine


class borrow(delegate.page):  # TODO: Why is this function defined twice?
    path = "/borrow"

    def GET(self):
        raise web.seeother('/subjects/in_library#ebooks=true')


class borrow(delegate.page):  # type: ignore[no-redef]
    path = "/borrow"
    encoding = "json"

    def is_enabled(self):
        return "inlibrary" in web.ctx.features

    @jsonapi
    def GET(self):
        i = web.input(
            offset=0, limit=12, rand=-1, details="false", has_fulltext="false"
        )

        filters = {}
        if i.get("has_fulltext") == "true":
            filters["has_fulltext"] = "true"

        if i.get("published_in"):
            if "-" in i.published_in:
                begin, end = i.published_in.split("-", 1)

                if (
                    h.safeint(begin, None) is not None
                    and h.safeint(end, None) is not None
                ):
                    filters["publish_year"] = [begin, end]
            else:
                y = h.safeint(i.published_in, None)
                if y is not None:
                    filters["publish_year"] = i.published_in

        i.limit = h.safeint(i.limit, 12)
        i.offset = h.safeint(i.offset, 0)

        i.rand = h.safeint(i.rand, -1)

        if i.rand > 0:
            sort = 'random_%d desc' % i.rand
            filters['sort'] = sort

        subject = get_lending_library(
            web.ctx.site,
            offset=i.offset,
            limit=i.limit,
            details=i.details.lower() == "true",
            inlibrary=False,
            **filters
        )
        return json.dumps(subject)


class read(delegate.page):  # TODO: Why is this function defined twice?
    path = "/read"

    def GET(self):
        web.seeother('/subjects/accessible_book#ebooks=true')


class read(delegate.page):  # type: ignore[no-redef]
    path = "/read"
    encoding = "json"

    @jsonapi
    def GET(self):
        i = web.input(
            offset=0, limit=12, rand=-1, details="false", has_fulltext="false"
        )

        filters = {}
        if i.get("has_fulltext") == "true":
            filters["has_fulltext"] = "true"

        if i.get("published_in"):
            if "-" in i.published_in:
                begin, end = i.published_in.split("-", 1)

                if (
                    h.safeint(begin, None) is not None
                    and h.safeint(end, None) is not None
                ):
                    filters["publish_year"] = [begin, end]
            else:
                y = h.safeint(i.published_in, None)
                if y is not None:
                    filters["publish_year"] = i.published_in

        i.limit = h.safeint(i.limit, 12)
        i.offset = h.safeint(i.offset, 0)

        i.rand = h.safeint(i.rand, -1)

        if i.rand > 0:
            sort = 'random_%d desc' % i.rand
            filters['sort'] = sort

        subject = get_readable_books(
            web.ctx.site,
            offset=i.offset,
            limit=i.limit,
            details=i.details.lower() == "true",
            **filters
        )
        return json.dumps(subject)


class borrow_about(delegate.page):
    path = "/borrow/about"

    def GET(self):
        raise web.notfound()


def convert_works_to_editions(site, works):
    """Takes work docs got from solr and converts them into appropriate editions required for lending library."""
    ekeys = [
        '/books/' + w['lending_edition'] for w in works if w.get('lending_edition')
    ]
    editions = {}
    for e in site.get_many(ekeys):
        editions[e['key']] = e.dict()

    for w in works:
        if w.get('lending_edition'):
            ekey = '/books/' + w['lending_edition']
            e = editions.get(ekey)
            if e and 'ocaid' in e:
                covers = e.get('covers') or [None]
                w['key'] = e['key']
                w['cover_id'] = covers[0]
                w['ia'] = e['ocaid']
                w['title'] = e.get('title') or w['title']


def get_lending_library(site, inlibrary=False, **kw):
    kw.setdefault("sort", "first_publish_year desc")

    if inlibrary:
        subject = CustomSubjectEngine().get_subject(
            "/subjects/lending_library", in_library=True, **kw
        )
    else:
        subject = CustomSubjectEngine().get_subject(
            "/subjects/lending_library", in_library=False, **kw
        )

    subject['key'] = '/borrow'
    convert_works_to_editions(site, subject['works'])
    return subject


def get_readable_books(site, **kw):
    kw.setdefault("sort", "first_publish_year desc")
    subject = ReadableBooksEngine().get_subject("/subjects/dummy", **kw)
    subject['key'] = '/read'
    return subject


class ReadableBooksEngine(SubjectEngine):
    """SubjectEngine for readable books.

    This doesn't take subject into account, but considers the public_scan_b
    field, which is derived from ia collections.

    There is a subject "/subjects/accessible_book", but it has some
    inlibrary/lendinglibrary books as well because of errors in OL data. Using
    public_scan_b derived from ia collections is more accurate.
    """

    def make_query(self, key, filters):
        return {"public_scan_b": "true"}

    def get_ebook_count(self, name, value, publish_year):
        # we are not displaying ebook count.
        # No point making a solr query
        return 0


class CustomSubjectEngine(SubjectEngine):
    """SubjectEngine for inlibrary and lending_library combined."""

    def make_query(self, key, filters):
        meta = self.get_meta(key)

        q = {
            meta.facet_key: ["lending_library"],
            'public_scan_b': "false",
            'NOT borrowed_b': "true",
            # show only books in last 20 or so years
            'publish_year': (str(1990), str(datetime.date.today().year)),  # range
        }

        if filters:
            if filters.get('in_library') is True:
                q[meta.facet_key].append('in_library')
            if filters.get("has_fulltext") == "true":
                q['has_fulltext'] = "true"
            if filters.get("publish_year"):
                q['publish_year'] = filters['publish_year']

        return q

    def get_ebook_count(self, name, value, publish_year):
        # we are not displaying ebook count.
        # No point making a solr query
        return 0


def on_loan_created_statsdb(loan):
    """Adds the loan info to the stats database."""
    key = _get_loan_key(loan)
    t_start = datetime.datetime.utcfromtimestamp(loan['loaned_at'])
    d = {
        "book": loan['book'],
        "identifier": loan['ocaid'],
        "resource_type": loan['resource_type'],
        "t_start": t_start.isoformat(),
        "status": "active",
    }
    d['library'] = "/libraries/internet_archive"
    d['geoip_country'] = None  # we removed geoip
    statsdb.add_entry(key, d)


def on_loan_completed_statsdb(loan):
    """Marks the loan as completed in the stats database."""
    key = _get_loan_key(loan)
    t_start = datetime.datetime.utcfromtimestamp(loan['loaned_at'])
    t_end = datetime.datetime.utcfromtimestamp(loan['returned_at'])
    d = {
        "book": loan['book'],
        "identifier": loan['ocaid'],
        "resource_type": loan['resource_type'],
        "t_start": t_start.isoformat(),
        "t_end": t_end.isoformat(),
        "status": "completed",
    }
    old = statsdb.get_entry(key)
    if old:
        olddata = json.loads(old.json)
        d = dict(olddata, **d)
    statsdb.update_entry(key, d)


def _get_loan_key(loan):
    # The loan key is now changed from uuid to fixed key.
    # Using _key as key for loan stats will result in overwriting previous loans.
    # Using the unique uuid to create the loan key and falling back to _key
    # when uuid is not available.
    return "loans/" + loan.get("uuid") or loan["_key"]


def setup():
    eventer.bind("loan-created", on_loan_created_statsdb)
    eventer.bind("loan-completed", on_loan_completed_statsdb)
