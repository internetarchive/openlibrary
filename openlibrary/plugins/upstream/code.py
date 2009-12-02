"""Upstream customizations."""

import os.path
import web
import random
import simplejson
import md5

from infogami import config
from infogami.utils import delegate, app, types
from infogami.utils.view import public

from infogami.plugins.api.code import jsonapi

from openlibrary.plugins.openlibrary.processors import ReadableUrlProcessor
from openlibrary.plugins.openlibrary import code as ol_code

import utils
import addbook
import models

if not config.get('coverstore_url'):
    config.coverstore_url = "http://covers.openlibrary.org"

class static(delegate.page):
    path = "/(?:images|css|js)/.*"
    def GET(self):
        page = web.ctx.site.get(web.ctx.path)
        if page and page.type.key != '/type/delete':
            return self.delegate()
        elif web.input(m=None).m is not None:
            return self.delegate()
        else:
            raise web.seeother('/static/upstream' + web.ctx.path)

    def POST(self):
        return self.delegate()

    def delegate(self):
        cls, args = app.find_mode()
        method = web.ctx.method

        if cls is None:
            raise web.seeother(web.changequery(m=None))
        elif not hasattr(cls, method):
            raise web.nomethod(method)
        else:
            return getattr(cls(), method)(*args)

# handlers for change photo and change cover

class change_cover(delegate.page):
    path = "(/books/OL\d+M)/cover"
    def GET(self, key):
        return ol_code.change_cover().GET(key)
    
class change_photo(change_cover):
    path = "(/authors/OL\d+A)/photo"

del delegate.modes['change_cover']     # delete change_cover mode added by openlibrary plugin

class subject_covers(delegate.page):
    path = "(/subjects(?:/places|/people|)/[^/]*)/covers"
    encoding = "json"
    
    @jsonapi
    def GET(self, key):
        page = web.ctx.site.get(key)
        if page is None:
            raise web.notfound("")
        else:
            i = web.input(offset=0, limit=20)
            try:
                offset = int(i.offset)
                limit = int(i.limit)
            except ValueError:
                return []
            data = page.get_covers(offset, limit)
            return simplejson.dumps(data)

@web.memoize
@public
def vendor_js():
    pardir = os.path.pardir 
    path = os.path.abspath(os.path.join(__file__, pardir, pardir, pardir, pardir, 'static', 'upstream', 'js', 'vendor.js'))
    digest = md5.md5(open(path).read()).hexdigest()
    return '/js/vendor.js?v=' + digest

class redirects(delegate.page):
    path = "/(a|b|user)/(.*)"
    def GET(self, prefix, path):
        d = dict(a="authors", b="books", user="people")
        raise web.redirect("/%s/%s" % (d[prefix], path))

@public
def get_document(key):
    return web.ctx.site.get(key)

def setup():
    """Setup for upstream plugin"""
    models.setup()
    utils.setup()
    addbook.setup()

    # overwrite ReadableUrlProcessor patterns for upstream
    ReadableUrlProcessor.patterns = [
        (r'/books/OL\d+M', '/type/edition', 'title', 'untitled'),
        (r'/authors/OL\d+A', '/type/author', 'name', 'noname'),
        (r'/works/OL\d+W', '/type/work', 'title', 'untitled')
    ]

    # Types for upstream paths
    types.register_type('^/authors/[^/]*$', '/type/author')
    types.register_type('^/books/[^/]*$', '/type/edition')
    types.register_type('^/languages/[^/]*$', '/type/language')

    types.register_type('^/subjects/places/[^/]*$', '/type/place')
    types.register_type('^/subjects/people/[^/]*$', '/type/person')
    types.register_type('^/subjects/[^/]*$', '/type/subject')

    # fix photo/cover url pattern
    ol_code.Author.photo_url_patten = "%s/photo"
    ol_code.Edition.cover_url_patten = "%s/cover"

    # setup template globals
    from openlibrary.i18n import gettext as _
        
    web.template.Template.globals['gettext'] = _
    web.template.Template.globals['_'] = _
    web.template.Template.globals['random'] = random.Random()
    
setup()
