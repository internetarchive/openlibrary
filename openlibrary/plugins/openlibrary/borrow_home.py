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
        subject = get_lending_library(details=True)
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

        subject = get_lending_library(offset=i.offset, limit=i.limit, details=i.details.lower() == "true", **filters)
        return simplejson.dumps(subject)

def get_lending_library(**kw):
    subject = worksearch.get_subject("/subjects/lending_library", **kw)
    subject['key'] = '/borrow'
    return subject

def setup():
    pass
    
    