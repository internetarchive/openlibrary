"""Controller for /borrow page.
"""
import simplejson
import web

from infogami.plugins.api.code import jsonapi
from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary.core import helpers as h
from openlibrary.plugins.worksearch import code as worksearch

class borrow(delegate.page):
    path = "/borrow"
    
    def is_enabled(self):
        return "inlibrary" in web.ctx.features
    
    def GET(self):
        subject = get_lending_library(web.ctx.site, details=True)
        return render_template("borrow/index", subject)

class borrow(delegate.page):
    path = "/borrow"
    encoding = "json"

    def is_enabled(self):
        return "inlibrary" in web.ctx.features

    @jsonapi
    def GET(self):
        i = web.input(offset=0, limit=12, details="false", has_fulltext="false")

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

        subject = get_lending_library(web.ctx.site, offset=i.offset, limit=i.limit, details=i.details.lower() == "true", **filters)
        return simplejson.dumps(subject)
        
def convert_works_to_editions(site, works):
    """Takes work docs got from solr and converts them into appropriate editions required for lending library.
    """
    ekeys = ['/books/' + w['lending_edition'] for w in works if w.get('lending_edition')]
    editions = {}
    for e in site.get_many(ekeys):
        editions[e['key']] = e.dict()
    
    for w in works:
        if w.get('lending_edition'):
            e = editions['/books/' + w['lending_edition']]
            if 'ocaid' in e:
                covers = e.get('covers') or [None]
                w['key'] = e['key']
                w['cover_id'] = covers[0]
                w['ia'] = e['ocaid']
                w['title'] = e.get('title') or w['title']

def get_lending_library(site, **kw):
    subject = worksearch.get_subject("/subjects/lending_library", **kw)
    subject['key'] = '/borrow'
    convert_works_to_editions(site, subject['works'])
    return subject

def setup():
    pass
    
    