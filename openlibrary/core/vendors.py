import re
import urllib2
import simplejson
from infogami.utils.view import public
from . import lending, cache, helpers as h
from openlibrary.utils import dateutil
from openlibrary.utils.isbn import (
    normalize_isbn, isbn_13_to_isbn_10, isbn_10_to_isbn_13)


BETTERWORLDBOOKS_API_URL = 'http://products.betterworldbooks.com/service.aspx?ItemId='

@public
def get_amazon_metadata(isbn):
    try:
        isbn = normalize_isbn(isbn)
        if isbn:
            return cached_get_amazon_metadata(isbn)
    except Exception:
        return None

def _get_amazon_metadata(isbn):
    # XXX some esbns may be < 10!
    isbn_10 = isbn if len(isbn) == 10 else isbn_13_to_isbn_10(isbn)
    isbn_13 = isbn if len(isbn) == 13 else isbn_10_to_isbn_13(isbn)
    try:
        if not lending.amazon_api:
            raise Exception
        product = lending.amazon_api.lookup(ItemId=isbn_10)
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
        'price': price_fmt,
        'price_amt': price,
        'qlt': qlt,
        'title': product.title,
        'authors': [{'name': name} for name in product.authors],
        'publish_date': product.publication_date.strftime('%b %d, %Y'),
        'source_records': ['amazon:%s' % product.asin],
        'number_of_pages': product.pages,
        'languages': list(product.languages),  # needs to be normalized
        'publishers': [product.publisher],
        'cover': product.large_image_url,
        'isbn_10': [isbn_10],
        'isbn_13': [isbn_13]
    }

@public
def get_betterworldbooks_metadata(isbn):
    try:
        isbn = normalize_isbn(isbn)
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
        return result
    except urllib2.HTTPError as e:
        try:
            response = e.read()
        except simplejson.decoder.JSONDecodeError:
            return {'error': e.read(), 'code': e.code}
        return simplejson.loads(response)


cached_get_betterworldbooks_metadata = cache.memcache_memoize(
    _get_betterworldbooks_metadata, "upstream.code._get_betterworldbooks_metadata", timeout=dateutil.HALF_DAY_SECS)
