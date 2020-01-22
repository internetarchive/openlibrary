import re
import web
import urllib2
import simplejson
import requests
from decimal import Decimal
from amazon.api import SearchException
from infogami import config
from infogami.utils.view import public
from . import lending, cache, helpers as h
from openlibrary.utils import dateutil
from openlibrary.utils.isbn import (
    normalize_isbn, isbn_13_to_isbn_10, isbn_10_to_isbn_13)
from openlibrary.catalog.add_book import load
from openlibrary import accounts

BETTERWORLDBOOKS_BASE_URL = 'https://betterworldbooks.com'
BETTERWORLDBOOKS_API_URL = 'https://products.betterworldbooks.com/service.aspx?ItemId='
BWB_AFFILIATE_LINK = 'http://www.anrdoezrs.net/links/{}/type/dlg/http://www.betterworldbooks.com/-id-%s'.format(h.affiliate_id('betterworldbooks'))
AMAZON_FULL_DATE_RE = re.compile(r'\d{4}-\d\d-\d\d')
ISBD_UNIT_PUNCT = ' : '  # ISBD cataloging title-unit separator punctuation

@public
def get_amazon_metadata(id_, id_type='isbn'):
    """Main interface to Amazon LookupItem API. Will cache results.

    :param str id_: The item id: isbn (10/13), or Amazon ASIN.
    :param str id_type: 'isbn' or 'asin'.
    :return: A single book item's metadata, or None.
    :rtype: dict or None
    """

    try:
        if id_:
            return cached_get_amazon_metadata(id_, id_type=id_type)
    except Exception:
        return None


def search_amazon(title='', author=''):
    """Uses the Amazon Product Advertising API ItemSearch operation to search for
    books by author and/or title.
    https://docs.aws.amazon.com/AWSECommerceService/latest/DG/ItemSearch.html

    :param str title: title of book to search for.
    :param str author: author name of book to search for.
    :return: dict of "results", a list of one or more found books, with metadata.
    :rtype: dict
    """

    results = lending.amazon_api.search(Title=title, Author=author, SearchIndex='Books')
    data = {'results': []}
    try:
        for product in results:
            data['results'].append(_serialize_amazon_product(product))
    except SearchException:
        data = {'error': 'no results'}
    return data


def _serialize_amazon_product(product):
    """Takes a full Amazon product Advertising API returned AmazonProduct
    with multiple ResponseGroups, and extracts the data we are interested in.

    :param amazon.api.AmazonProduct product:
    :return: Amazon metadata for one product
    :rtype: dict
    """

    price_fmt = price = qlt = None
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
            product.asin, h.affiliate_id('amazon')),
        'price': price_fmt,
        'price_amt': price,
        'qlt': qlt,
        'title': product.title,
        'authors': [{'name': name} for name in product.authors],
        'source_records': ['amazon:%s' % product.asin],
        'number_of_pages': product.pages,
        'languages': list(product.languages),
        'cover': product.large_image_url,
        'product_group': product.product_group,
    }
    if product._safe_get_element('OfferSummary') is not None:
        data['offer_summary'] = {
            'total_new': int(product._safe_get_element_text('OfferSummary.TotalNew')),
            'total_used': int(product._safe_get_element_text('OfferSummary.TotalUsed')),
            'total_collectible': int(product._safe_get_element_text('OfferSummary.TotalCollectible')),
        }
        collectible = product._safe_get_element_text('OfferSummary.LowestCollectiblePrice.Amount')
        if new:
            data['offer_summary']['lowest_new'] = int(new)
        if used:
            data['offer_summary']['lowest_used'] = int(used)
        if collectible:
            data['offer_summary']['lowest_collectible'] = int(collectible)
        amazon_offers = product._safe_get_element_text('Offers.TotalOffers')
        if amazon_offers:
            data['offer_summary']['amazon_offers'] = int(amazon_offers)

    if product.publication_date:
        data['publish_date'] = product._safe_get_element_text('ItemAttributes.PublicationDate')
        if re.match(AMAZON_FULL_DATE_RE, data['publish_date']):
            data['publish_date'] = product.publication_date.strftime('%b %d, %Y')

    if product.binding:
        data['physical_format'] = product.binding.lower()
    if product.edition:
        data['edition'] = product.edition
    if product.publisher:
        data['publishers'] = [product.publisher]
    if product.isbn:
        isbn = product.isbn
        if len(isbn) == 10:
            data['isbn_10'] = [isbn]
            data['isbn_13'] = [isbn_10_to_isbn_13(isbn)]
        elif len(isbn) == 13:
            data['isbn_13'] = [isbn]
            if isbn.startswith('978'):
                data['isbn_10'] = [isbn_13_to_isbn_10(isbn)]
    return data


def _get_amazon_metadata(id_=None, id_type='isbn'):
    """Uses the Amazon Product Advertising API ItemLookup operation to locatate a
    specific book by identifier; either 'isbn' or 'asin'.
    https://docs.aws.amazon.com/AWSECommerceService/latest/DG/ItemLookup.html

    :param str id_: The item id: isbn (10/13), or Amazon ASIN.
    :param str id_type: 'isbn' or 'asin'.
    :return: A single book item's metadata, or None.
    :rtype: dict or None
    """

    kwargs = {}
    if id_type == 'isbn':
        id_ = normalize_isbn(id_)
        kwargs = {'SearchIndex': 'Books', 'IdType': 'ISBN'}
    kwargs['ItemId'] = id_
    kwargs['MerchantId'] = 'Amazon'  # Only affects Offers Response Group, does Amazon sell this directly?
    try:
        if not lending.amazon_api:
            raise Exception
        product = lending.amazon_api.lookup(**kwargs)
        # sometimes more than one product can be returned, choose first
        if isinstance(product, list):
            product = product[0]
    except Exception as e:
        return None

    return _serialize_amazon_product(product)


def split_amazon_title(full_title):
    """Splits an Amazon title into (title, subtitle),
    strips parenthetical tags.
    :param str full_title:
    :rtype: (str, str | None)
    :return: (title, subtitle | None)
    """

    # strip parenthetical blocks wherever they occur
    # can handle 1 level of nesting
    re_parens_strip = re.compile(r'\(([^\)\(]*|[^\(]*\([^\)]*\)[^\)]*)\)')
    full_title = re.sub(re_parens_strip, '', full_title)

    titles = full_title.split(':')
    subtitle = titles.pop().strip() if len(titles) > 1 else None
    title = ISBD_UNIT_PUNCT.join([unit.strip() for unit in titles])
    return (title, subtitle)


def clean_amazon_metadata_for_load(metadata):
    """This is a bootstrapping helper method which enables us to take the
    results of get_amazon_metadata() and create an
    OL book catalog record.

    :param dict metadata: Metadata representing an Amazon product.
    :return: A dict representing a book suitable for importing into OL.
    :rtype: dict
    """

    # TODO: convert languages into /type/language list
    conforming_fields = [
        'title', 'authors', 'publish_date', 'source_records',
        'number_of_pages', 'publishers', 'cover', 'isbn_10',
        'isbn_13', 'physical_format']
    conforming_metadata = {}
    for k in conforming_fields:
        # if valid key and value not None
        if metadata.get(k) is not None:
            conforming_metadata[k] = metadata[k]
    if metadata.get('source_records'):
        asin = metadata.get('source_records')[0].replace('amazon:', '')
        if asin[0].isalpha():
            # Only store asin if it provides more information than ISBN
            conforming_metadata['identifiers'] = {'amazon': [asin]}
    title, subtitle = split_amazon_title(metadata['title'])
    conforming_metadata['title'] = title
    if subtitle:
        conforming_metadata['full_title'] = title + ISBD_UNIT_PUNCT + subtitle
        conforming_metadata['subtitle'] = subtitle
    # Record original title if some content has been removed (i.e. parentheses)
    if metadata['title'] != conforming_metadata.get('full_title', conforming_metadata['title']):
        conforming_metadata['notes'] = "Source title: %s" % metadata['title']

    return conforming_metadata


def create_edition_from_amazon_metadata(id_, id_type='isbn'):
    """Fetches Amazon metadata by id from Amazon Product Advertising API, attempts to
    create OL edition from metadata, and returns the resulting edition
    key `/key/OL..M` if successful or None otherwise.

    :param str id_: The item id: isbn (10/13), or Amazon ASIN.
    :param str id_type: 'isbn' or 'asin'.
    :return: Edition key '/key/OL..M' or None
    :rtype: str or None
    """

    md = get_amazon_metadata(id_, id_type=id_type)

    if md and md.get('product_group') == 'Book':
        with accounts.RunAs('ImportBot'):
            reply = load(
                clean_amazon_metadata_for_load(md),
                account=accounts.get_current_user())
            if reply and reply.get('success'):
                return reply['edition'].get('key')


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
def get_betterworldbooks_metadata(isbn, thirdparty=False):
    """
    :param str isbn: Unnormalisied ISBN10 or ISBN13
    :param bool thirdparty: If no Product API  match, scrape bwb website for 3rd party matches
    :return: Metadata for a single BWB book, currently listed on their catalog, or error dict.
    :rtype: dict
    """

    isbn = normalize_isbn(isbn)
    try:
        metadata = _get_betterworldbooks_metadata(isbn)
        if not metadata.get('price') and thirdparty:
            return _get_betterworldbooks_thirdparty_metadata(isbn)
        return metadata
    except Exception:
        return betterworldbooks_fmt(isbn)

def _get_betterworldbooks_thirdparty_metadata(isbn):
    """Scrapes metadata from betterworldbooks website in the case the
    Product API returns no result (i.e. includes 3rd party vendor inventory)

    :param str isbn: Unnormalised ISBN10 or ISBN13
    :return: Metadata for a single BWB book, currently listed on their catalog, or error dict.
    :rtype: dict
    """
    url = '%s/product/detail/-%s' % (BETTERWORLDBOOKS_BASE_URL, isbn)
    content = requests.get(url).text
    results = [betterworldbooks_fmt(
        isbn,
        qlt=i[0].lower(),
        price=i[1]
    ) for i in re.findall('data-condition="(New|Used).*data-price="([0-9.]+)"', content)]
    cheapest = sorted(results, key=lambda i: Decimal(i['price_amt']))[0]
    return cheapest

def _get_betterworldbooks_metadata(isbn):
    """Returns price and other metadata (currently minimal)
    for a book currently available on betterworldbooks.com

    :param str isbn: Normalised ISBN10 or ISBN13
    :return: Metadata for a single BWB book currently listed on their catalog, or error dict.
    :rtype: dict
    """

    url = BETTERWORLDBOOKS_API_URL + isbn
    try:
        response = requests.get(url).content
        new_qty = re.findall("<TotalNew>([0-9]+)</TotalNew>", response)
        new_price = re.findall(r"<LowestNewPrice>\$([0-9.]+)</LowestNewPrice>", response)
        used_price = re.findall(r"<LowestUsedPrice>\$([0-9.]+)</LowestUsedPrice>", response)
        used_qty = re.findall("<TotalUsed>([0-9]+)</TotalUsed>", response)

        price = qlt = None

        if used_qty and used_qty[0] and used_qty[0] != '0':
            price = used_price[0] if used_price else ''
            qlt = 'used'

        if new_qty and new_qty[0] and new_qty[0] != '0':
            _price = new_price[0] if new_price else None
            if _price and (not price or float(_price) < float(price)):
                price = _price
                qlt = 'new'

        return betterworldbooks_fmt(isbn, qlt, price)

    except urllib2.HTTPError as e:
        try:
            response = e.read()
        except simplejson.decoder.JSONDecodeError:
            return {'error': e.read(), 'code': e.code}
        return simplejson.loads(response)

def betterworldbooks_fmt(isbn, qlt=None, price=None):
    """Defines a standard interface for returning bwb price info

    :param str isbn:
    :param str qlt: Quality of the book, e.g. "new", "used"
    :param str price: Price of the book as a decimal str, e.g. "4.28"
    :rtype: dict 
    """
    price_fmt = "$%s (%s)" % (price, qlt) if price and qlt else None
    return {
        'url': BWB_AFFILIATE_LINK % isbn,
        'isbn': isbn,
        'price': price_fmt,
        'price_amt': price,
        'qlt': qlt
    }


def check_bwb_scraper_status():
    """
    Check if the bwb scraper is still working; since it's checking
    HTML, we want to know if it's stopped working.
    :rtype: bool, str
    """
    # Pull a random (available) book from betterworldbooks
    content = requests.get(BETTERWORLDBOOKS_BASE_URL).text
    isbn = re.findall(r'isbn1="([0-9]+)"', content)[0]
    if not isbn:
        return False, 'ISBN missing from %s' % BETTERWORLDBOOKS_BASE_URL
    data = _get_betterworldbooks_thirdparty_metadata(isbn)
    return 'price_amt' in data, simplejson.dumps(data, indent=4 * ' ')


cached_get_betterworldbooks_metadata = cache.memcache_memoize(
    _get_betterworldbooks_metadata, "upstream.code._get_betterworldbooks_metadata", timeout=dateutil.HALF_DAY_SECS)
