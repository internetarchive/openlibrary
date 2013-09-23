"""Controller for /borrow page.
"""
import simplejson
import web
import random
import datetime

from infogami.plugins.api.code import jsonapi
from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary.core import helpers as h
from openlibrary.core import inlibrary
from openlibrary.plugins.worksearch.subjects import SubjectEngine

from libraries import LoanStats

class borrow(delegate.page):
    path = "/borrow"
    
    def is_enabled(self):
        return "inlibrary" in web.ctx.features
    
    def GET(self):
        rand = random.randint(0, 9999)
        sort = "random_%d desc" % rand
        is_inlibrary = inlibrary.get_library() is not None
        subject = get_lending_library(web.ctx.site, details=True, inlibrary=is_inlibrary, limit=24, sort=sort)
        return render_template("borrow/index", subject, stats=LoanStats(), rand=rand, inlibrary=is_inlibrary)

class borrow(delegate.page):
    path = "/borrow"
    encoding = "json"

    def is_enabled(self):
        return "inlibrary" in web.ctx.features

    @jsonapi
    def GET(self):
        i = web.input(offset=0, limit=24, rand=-1, details="false", has_fulltext="false")

        filters = {}
        if i.get("has_fulltext") == "true":
            filters["has_fulltext"] = "true"

        if i.get("published_in"):
            if "-" in i.published_in:
                begin, end = i.published_in.split("-", 1)

                if h.safeint(begin, None) is not None and h.safeint(end, None) is not None:
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

        subject = get_lending_library(web.ctx.site, 
            offset=i.offset, 
            limit=i.limit, 
            details=i.details.lower() == "true", 
            inlibrary=inlibrary.get_library() is not None,
            **filters)
        return simplejson.dumps(subject)

class read(delegate.page):
    path = "/read"
    
    def GET(self):
        rand = random.randint(0, 9999)
        sort = "random_%d desc" % rand
        subject = get_readable_books(web.ctx.site, details=True, limit=24, sort=sort)
        return render_template("borrow/read", subject, stats=LoanStats(), rand=rand)

class read(delegate.page):
    path = "/read"
    encoding = "json"

    @jsonapi
    def GET(self):
        i = web.input(offset=0, limit=24, rand=-1, details="false", has_fulltext="false")

        filters = {}
        if i.get("has_fulltext") == "true":
            filters["has_fulltext"] = "true"

        if i.get("published_in"):
            if "-" in i.published_in:
                begin, end = i.published_in.split("-", 1)

                if h.safeint(begin, None) is not None and h.safeint(end, None) is not None:
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

        subject = get_readable_books(web.ctx.site, 
            offset=i.offset, 
            limit=i.limit, 
            details=i.details.lower() == "true",
            **filters)
        return simplejson.dumps(subject)

class borrow_about(delegate.page):
    path = "/borrow/about"
    
    def GET(self):
        return render_template("borrow/about")
        
def convert_works_to_editions(site, works):
    """Takes work docs got from solr and converts them into appropriate editions required for lending library.
    """
    ekeys = ['/books/' + w['lending_edition'] for w in works if w.get('lending_edition')]
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
        subject = CustomSubjectEngine().get_subject("/subjects/lending_library", in_library=True, **kw)
    else:
        subject = CustomSubjectEngine().get_subject("/subjects/lending_library", in_library=False, **kw)
    
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
        return {
            "public_scan_b": "true"
        }

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
            'publish_year': (str(1990), str(datetime.date.today().year)) # range
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


def setup():
    pass
