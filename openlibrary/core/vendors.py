import re
import web
import urllib2
import simplejson
from infogami import config
from infogami.utils.view import public
from . import lending, cache, helpers as h
from openlibrary.utils import dateutil
from openlibrary.utils.isbn import (
    normalize_isbn, isbn_13_to_isbn_10, isbn_10_to_isbn_13)
from openlibrary.catalog.add_book import load
from openlibrary import accounts

BETTERWORLDBOOKS_API_URL = 'http://products.betterworldbooks.com/service.aspx?ItemId='

@public
def get_amazon_metadata(isbn):
    try:
        isbn = normalize_isbn(isbn)
        if isbn:
            return cached_get_amazon_metadata(isbn)
    except Exception:
        return None

def _get_amazon_metadata(isbn=None):
    # XXX @hornc, you should be extending this to work with
    # isbn=, asin=, title=, authors=, etc
    isbn = normalize_isbn(isbn)
    try:
        if not lending.amazon_api:
            raise Exception
        product = lending.amazon_api.lookup(
            ItemId=isbn, IdType="ISBN", SearchIndex="Books")
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

    data = {
        'url': "https://www.amazon.com/dp/%s/?tag=%s" % (
            isbn, h.affiliate_id('amazon')),
        'price': price_fmt,
        'price_amt': price,
        'qlt': qlt,
        'title': product.title,
        'authors': [{'name': name} for name in product.authors],
        'publish_date': product.publication_date.strftime('%b %d, %Y'),
        'source_records': ['amazon:%s' % product.asin],
        'number_of_pages': product.pages,
        'languages': list(product.languages),  # needs to be normalized
        'cover': product.large_image_url,
    }
    if product.publisher:
        data['publishers'] = [product.publisher]
    if len(isbn) == 10:
        data['isbn_10'] = [isbn]
        data['isbn_13'] = [isbn_10_to_isbn_13(isbn)]
    if len(isbn) == 13:
        data['isbn_13'] = [isbn]
        if isbn.startswith('978'):
            data['isbn_10'] = [isbn_13_to_isbn_10(isbn)]
    return data

def clean_amazon_metadata_for_load(metadata):
    """This is a bootstrapping helper method which enables us to take the
    results of plugins.upstream.code.get_amazon_metadata and create an
    OL book catalog record
    """    
    conforming_fields = [
        'title', 'authors', 'publish_date', 'source_records',
        'number_of_pages', 'publishers', 'cover', 'isbn_10',
        'isbn_13']
    conforming_metadata = {}
    for k in conforming_fields:
        # if valid key and value not None
        if metadata.get(k) is not None:
            conforming_metadata[k] = metadata[k]
    return conforming_metadata

def create_edition_from_amazon_metadata(isbn):
    """Fetches amazon metadata by isbn from affiliates API, attempts to
    create OL edition from metadata, and returns the resulting edition key
    `/key/OL..M` if successful or None otherwise
    """
    md = get_amazon_metadata(isbn)
    if md:
        # Save token of currently logged in user (or no-user)
        account = accounts.get_current_user()
        auth_token = account.generate_login_code() if account else ''

        try:
            # Temporarily behave (act) as ImportBot for import
            tmp_account = accounts.find(username='ImportBot')
            web.ctx.conn.set_auth_token(tmp_account.generate_login_code())
            reply = load(clean_amazon_metadata_for_load(md),
                         account=tmp_account)
        except Exception as e:
            web.ctx.conn.set_auth_token(auth_token)
            raise e

        # Return auth token to original user or no-user
        web.ctx.conn.set_auth_token(auth_token)

        if reply and reply.get('success'):
            return reply['edition']['key']

@public
def get_betterworldbooks_metadata(isbn):
    isbn = normalize_isbn(isbn)
    try:
        if isbn:
            return _get_betterworldbooks_metadata(isbn)
    except Exception:
        return {}

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
                    h.affiliate_id('betterworldbooks'), isbn)),
            'price': price_fmt,
            'price_amt': price,
            'qlt': qlt
        }
    except urllib2.HTTPError as e:
        try:
            response = e.read()
        except simplejson.decoder.JSONDecodeError:
            return {'error': e.read(), 'code': e.code}
        return simplejson.loads(response)


cached_get_betterworldbooks_metadata = cache.memcache_memoize(
    _get_betterworldbooks_metadata, "upstream.code._get_betterworldbooks_metadata", timeout=dateutil.HALF_DAY_SECS)
