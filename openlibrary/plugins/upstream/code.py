"""Upstream customizations."""

import os.path
import web
import random
import simplejson
import md5
import re
import datetime
import urllib2
import logging

from infogami import config
from infogami.infobase import client
from infogami.utils import delegate, app, types
from infogami.utils.view import public, safeint, render
from infogami.utils.context import context

from utils import render_template

from openlibrary.core import cache, helpers as h
from openlibrary.core.lending import amazon_api
from openlibrary import accounts
from openlibrary.utils import dateutil
from openlibrary.plugins.openlibrary.processors import ReadableUrlProcessor
from openlibrary.plugins.openlibrary import code as ol_code

import utils
import addbook
import models
import covers
import borrow
import recentchanges
import merge_authors

logger = logging.getLogger("openlibrary.plugins")

BETTERWORLDBOOKS_API_URL = 'http://products.betterworldbooks.com/service.aspx?ItemId='

if not config.get('coverstore_url'):
    config.coverstore_url = "https://covers.openlibrary.org"

class static(delegate.page):
    path = "/images/.*"
    def GET(self):
        host = 'https://%s' % web.ctx.host if 'openlibrary.org' in web.ctx.host else ''
        raise web.seeother(host + '/static' + web.ctx.path)

# handlers for change photo and change cover

class change_cover(delegate.page):
    path = "(/books/OL\d+M)/cover"
    def GET(self, key):
        return ol_code.change_cover().GET(key)

class change_photo(change_cover):
    path = "(/authors/OL\d+A)/photo"

del delegate.modes['change_cover']     # delete change_cover mode added by openlibrary plugin

class merge_work(delegate.page):
    path = "(/works/OL\d+W)/merge"
    def GET(self, key):
        return "This looks like a good place for a merge UI!"

    def POST(self, key):
        pass

@web.memoize
@public
def vendor_js():
    pardir = os.path.pardir
    path = os.path.abspath(os.path.join(__file__, pardir, pardir, pardir, pardir, 'static', 'upstream', 'js', 'vendor.js'))
    digest = md5.md5(open(path).read()).hexdigest()
    return '/static/upstream/js/vendor.js?v=' + digest

@web.memoize
@public
def static_url(path):
    """Takes path relative to static/ and constructs url to that resource with hash.
    """
    pardir = os.path.pardir
    fullpath = os.path.abspath(os.path.join(__file__, pardir, pardir, pardir, pardir, "static", path))
    digest = md5.md5(open(fullpath).read()).hexdigest()
    return "/static/%s?v=%s" % (path, digest)


def normalize_isbn(isbn):
    _isbn = isbn.replace(' ', '').strip()
    if len(re.findall('[0-9X]+', isbn)) and len(isbn) in [10, 13]:
        return _isbn

@public
def get_amazon_metadata(isbn):
    try:
        isbn = normalize_isbn(isbn)
        if isbn:
            return cached_get_amazon_metadata(isbn)
    except Exception:
        return None

def _get_amazon_metadata(isbn):
    try:
        if not amazon_api:
            logger.info("Amazon keys likely misconfigured")
            raise Exception
        product = amazon_api.lookup(ItemId=isbn)
    except Exception as e:
        return None

    price_fmt, price, qlt = (None, None, None)
    used = product._safe_get_element_text('OfferSummary.LowestUsedPrice.Amount')
    new = product._safe_get_element_text('OfferSummary.LowestNewPrice.Amount')

    # prioritize lower prices and newer, all things being equal
    if used and new:
        price, qlt = (used, 'used') if int(used) < int(new) else (new, 'new')
    # accept whichever is available
    elif used or new:
        price, qlt = (used, 'used') if used else (new, 'new')

    if price:
        price = '{:00,.2f}'.format(int(price)/100.)
        if qlt:
            price_fmt = "$%s (%s)" % (price, qlt)

    return {
        'url': "https://www.amazon.com/dp/%s/?tag=%s" % (
            isbn, h.affiliate_id('amazon')),
        'price_fmt': price_fmt,
        'price': price,
        'qlt': qlt,
    }


def cached_get_amazon_metadata(*args, **kwargs):
    """If the cached data is `None`, likely a 503 throttling occurred on
    Amazon's side. Try again to fetch the value instead of using the
    cached value. It may 503 again, in which case the next access of
    this page will trigger another re-cache. If the amazon API call
    succeeds but the book has no price data, then {"price": None} will
    be cached as to not trigger a re-cache (only the value `None`
    will cause re-cache)
    """
    # fetch/compose a cache controller obj for
    # "upstream.code._get_amazon_metadata"
    memoized_get_amazon_metadata = cache.memcache_memoize(
        _get_amazon_metadata, "upstream.code._get_amazon_metadata",
        timeout=dateutil.WEEK_SECS)
    # fetch cached value from this controller
    result = memoized_get_amazon_metadata(*args, **kwargs)
    if result is None:
        # recache / update this controller's cached value
        # (corresponding to these input args)
        result = memoized_get_amazon_metadata.update(*args, **kwargs)[0]
    return result

@public
def get_betterworldbooks_metadata(isbn):
    try:
        isbn = normalize_isbn(isbn)
        if isbn:
            return _get_betterworldbooks_metadata(isbn)
    except Exception:
        return {}

def _get_betterworldbooks_metadata(isbn):
    url = BETTERWORLDBOOKS_API_URL + isbn
    try:
        req = urllib2.Request(url)
        f = urllib2.urlopen(req)
        response = f.read()
        f.close()
        product_url = re.findall("<DetailURLPage>\$(.+)</DetailURLPage>", response)
        new_qty = re.findall("<TotalNew>([0-9]+)</TotalNew>", response)
        new_price = re.findall("<LowestNewPrice>\$([0-9.]+)</LowestNewPrice>", response)
        used_price = re.findall("<LowestUsedPrice>\$([0-9.]+)</LowestUsedPrice>", response)
        used_qty = re.findall("<TotalUsed>([0-9]+)</TotalUsed>", response)

        price_fmt, price, qlt = None, None, None

        if used_qty and used_qty[0] and used_qty[0] != '0':
            price = used_price[0] if used_price else ''
            qlt = 'used'

        if new_qty and new_qty[0] and new_qty[0] != '0':
            _price = used_price[0] if used_price else None
            if price and _price and _price < price:
                price = _price
                qlt = 'new'

        if price and qlt:
            price_fmt = "$%s (%s)" % (price, qlt)

        return {
            'url': (
                'http://www.anrdoezrs.net/links/'
                '%s/type/dlg/http://www.betterworldbooks.com/-id-%s.aspx' % (
                    isbn, h.affiliate_id('betterworldbooks'))),
            'price': price,
            'qlt': qlt,
            'price_fmt': price_fmt
        }
        return result
    except urllib2.HTTPError as e:
        try:
            response = e.read()
        except simplejson.decoder.JSONDecodeError:
            return {'error': e.read(), 'code': e.code}
        return simplejson.loads(response)


cached_get_betterworldbooks_metadata = cache.memcache_memoize(
    _get_betterworldbooks_metadata, "upstream.code._get_betterworldbooks_metadata", timeout=dateutil.HALF_DAY_SECS)

class DynamicDocument:
    """Dynamic document is created by concatinating various rawtext documents in the DB.
    Used to generate combined js/css using multiple js/css files in the system.
    """
    def __init__(self, root):
        self.root = web.rstrips(root, '/')
        self.docs = None
        self._text = None
        self.last_modified = None

    def update(self):
        keys = web.ctx.site.things({'type': '/type/rawtext', 'key~': self.root + '/*'})
        docs = sorted(web.ctx.site.get_many(keys), key=lambda doc: doc.key)
        if docs:
            self.last_modified = min(doc.last_modified for doc in docs)
            self._text = "\n\n".join(doc.get('body', '') for doc in docs)
        else:
            self.last_modified = datetime.datetime.utcnow()
            self._text = ""

    def get_text(self):
        """Returns text of the combined documents"""
        if self._text is None:
            self.update()
        return self._text

    def md5(self):
        """Returns md5 checksum of the combined documents"""
        return md5.md5(self.get_text()).hexdigest()

def create_dynamic_document(url, prefix):
    """Creates a handler for `url` for servering combined js/css for `prefix/*` pages"""
    doc = DynamicDocument(prefix)

    if url.endswith('.js'):
        content_type = "text/javascript"
    elif url.endswith(".css"):
        content_type = "text/css"
    else:
        content_type = "text/plain"

    class page(delegate.page):
        """Handler for serving the combined content."""
        path = "__registered_later_without_using_this__"
        def GET(self):
            i = web.input(v=None)
            v = doc.md5()
            if v != i.v:
                raise web.seeother(web.changequery(v=v))

            if web.modified(etag=v):
                oneyear = 365 * 24 * 3600
                web.header("Content-Type", content_type)
                web.header("Cache-Control", "Public, max-age=%d" % oneyear)
                web.lastmodified(doc.last_modified)
                web.expires(oneyear)
                return delegate.RawText(doc.get_text())

        def url(self):
            return url + "?v=" + doc.md5()

        def reload(self):
            doc.update()

    class hook(client.hook):
        """Hook to update the DynamicDocument when any of the source pages is updated."""
        def on_new_version(self, page):
            if page.key.startswith(doc.root):
                doc.update()

    # register the special page
    delegate.pages[url] = {}
    delegate.pages[url][None] = page
    return page

all_js = create_dynamic_document("/js/all.js", config.get("js_root", "/js"))
web.template.Template.globals['all_js'] = all_js()

all_css = create_dynamic_document("/css/all.css", config.get("css_root", "/css"))
web.template.Template.globals['all_css'] = all_css()

def reload():
    """Reload all.css and all.js"""
    all_css().reload()
    all_js().reload()

def setup_jquery_urls():
    if config.get('use_google_cdn', True):
        jquery_url = "http://ajax.googleapis.com/ajax/libs/jquery/1.3.2/jquery.min.js"
        jqueryui_url = "http://ajax.googleapis.com/ajax/libs/jqueryui/1.7.2/jquery-ui.min.js"
    else:
        jquery_url = "/static/upstream/js/jquery-1.3.2.min.js"
        jqueryui_url = "/static/upstream/js/jquery-ui-1.7.2.min.js"

    web.template.Template.globals['jquery_url'] = jquery_url
    web.template.Template.globals['jqueryui_url'] = jqueryui_url
    web.template.Template.globals['use_google_cdn'] = config.get('use_google_cdn', True)

@public
def get_document(key):
    return web.ctx.site.get(key)

class revert(delegate.mode):
    def GET(self, key):
        raise web.seeother(web.changequery(m=None))

    def POST(self, key):
        i = web.input("v", _comment=None)
        v = i.v and safeint(i.v, None)

        if v is None:
            raise web.seeother(web.changequery({}))

        user = accounts.get_current_user()
        is_admin = user and user.key in [m.key for m in web.ctx.site.get('/usergroup/admin').members]
        if not (is_admin and web.ctx.site.can_write(key)):
            return render.permission_denied(web.ctx.fullpath, "Permission denied to edit " + key + ".")

        thing = web.ctx.site.get(key, i.v)

        if not thing:
            raise web.notfound()

        def revert(thing):
            if thing.type.key == "/type/delete" and thing.revision > 1:
                prev = web.ctx.site.get(thing.key, thing.revision-1)
                if prev.type.key in ["/type/delete", "/type/redirect"]:
                    return revert(prev)
                else:
                    prev._save("revert to revision %d" % prev.revision)
                    return prev
            elif thing.type.key == "/type/redirect":
                redirect = web.ctx.site.get(thing.location)
                if redirect and redirect.type.key not in ["/type/delete", "/type/redirect"]:
                    return redirect
                else:
                    # bad redirect. Try the previous revision
                    prev = web.ctx.site.get(thing.key, thing.revision-1)
                    return revert(prev)
            else:
                return thing

        def process(value):
            if isinstance(value, list):
                return [process(v) for v in value]
            elif isinstance(value, client.Thing):
                if value.key:
                    if value.type.key in ['/type/delete', '/type/revert']:
                        return revert(value)
                    else:
                        return value
                else:
                    for k in value.keys():
                        value[k] = process(value[k])
                    return value
            else:
                return value

        for k in thing.keys():
            thing[k] = process(thing[k])

        comment = i._comment or "reverted to revision %d" % v
        thing._save(comment)
        raise web.seeother(key)

def setup():
    """Setup for upstream plugin"""
    models.setup()
    utils.setup()
    addbook.setup()
    covers.setup()
    merge_authors.setup()

    import data
    data.setup()

    # setup template globals
    from openlibrary.i18n import ugettext, ungettext, gettext_territory

    web.template.Template.globals.update({
        "gettext": ugettext,
        "ugettext": ugettext,
        "_": ugettext,
        "ungettext": ungettext,
        "gettext_territory": gettext_territory,
        "random": random.Random(),
        "commify": web.commify,
        "group": web.group,
        "storage": web.storage,
        "all": all,
        "any": any,
        "locals": locals
    });

    import jsdef
    web.template.STATEMENT_NODES["jsdef"] = jsdef.JSDefNode

    setup_jquery_urls()
setup()
