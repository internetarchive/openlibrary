import logging
import re
import requests
import simplejson
import time
from dateutil import parser as isoparser
from decimal import Decimal

from paapi5_python_sdk.api.default_api import DefaultApi
from paapi5_python_sdk.get_items_request import GetItemsRequest
from paapi5_python_sdk.get_items_resource import GetItemsResource
from paapi5_python_sdk.partner_type import PartnerType
from paapi5_python_sdk.rest import ApiException

from infogami.utils.view import public
from openlibrary.core import lending, cache, helpers as h
from openlibrary.utils import dateutil
from openlibrary.utils.isbn import (
    normalize_isbn, isbn_13_to_isbn_10, isbn_10_to_isbn_13)
from openlibrary.catalog.add_book import load
from openlibrary import accounts


logger = logging.getLogger("openlibrary.vendors")

amazon_api = None
config_amz_api = None

BETTERWORLDBOOKS_BASE_URL = 'https://betterworldbooks.com'
BETTERWORLDBOOKS_API_URL = ('https://products.betterworldbooks.com/service.aspx?'
                            'IncludeAmazon=True&ItemId=')
BWB_AFFILIATE_LINK = 'http://www.anrdoezrs.net/links/{}/type/dlg/http://www.betterworldbooks.com/-id-%s'.format(h.affiliate_id('betterworldbooks'))
AMAZON_FULL_DATE_RE = re.compile(r'\d{4}-\d\d-\d\d')
ISBD_UNIT_PUNCT = ' : '  # ISBD cataloging title-unit separator punctuation


def setup(config):
    global config_amz_api, amazon_api
    config_amz_api = config.get('amazon_api')
    try:
        amazon_api = AmazonAPI(
            config_amz_api.key, config_amz_api.secret,
            config_amz_api.id, throttling=0.9)
    except AttributeError:
        amazon_api = None


class AmazonAPI:
    """Amazon Product Advertising API 5.0 wrapper for Python"""
    RESOURCES = {
        'all': [
            getattr(GetItemsResource, v) for v in
            # Hack: pulls all resource consts from GetItemsResource
            vars(GetItemsResource).keys() if v.isupper()
        ],
        'import': [
            GetItemsResource.IMAGES_PRIMARY_LARGE,
            GetItemsResource.ITEMINFO_BYLINEINFO,
            GetItemsResource.ITEMINFO_CONTENTINFO,
            GetItemsResource.ITEMINFO_MANUFACTUREINFO,
            GetItemsResource.ITEMINFO_PRODUCTINFO,
            GetItemsResource.ITEMINFO_TITLE,
            GetItemsResource.ITEMINFO_CLASSIFICATIONS,
            GetItemsResource.OFFERS_LISTINGS_PRICE,
        ],
        'prices': [
            GetItemsResource.OFFERS_LISTINGS_PRICE
        ]
    }


    def __init__(self, key, secret, tag, host='webservices.amazon.com',
                 region='us-east-1', throttling=0.9):
        """
        Creates an instance containing your API credentials.

        :param key (string): affiliate key
        :param secret (string): affiliate secret
        :param tag (string): affiliate string
        :param host (string): which server to query
        :param region (string): which regional host to query
        :param throttling (float): Reduce this value to wait longer
          between API calls.
        :return: Amazon metadata for one product
        :rtype: dict
        """
        self.tag = tag
        self.throttling = throttling
        self.last_query_time = time.time()

        self.api = DefaultApi(
            access_key=key,
            secret_key=secret,
            host=host,
            region=region)

    def get_product(self, asin, serialize=False, **kwargs):
        products = self.get_products([asin], **kwargs)
        if products:
            return next(self.serialize(p) if serialize else p for p in products)

    def get_products(self, asins, serialize=False, marketplace='www.amazon.com',
                     resources=None, **kwargs):
        """
        :param asins (string): One or more ItemIds like ASIN that
        uniquely identify an item or product URL. (Max 10) Seperated
        by comma or as a list.
        """
        # Wait before doing the request
        wait_time = 1 / self.throttling - (time.time() - self.last_query_time)
        if wait_time > 0:
            time.sleep(wait_time)
        self.last_query_time = time.time()

        item_ids = asins if type(asins) is list else [asins]
        _resources = self.RESOURCES[resources or 'import']
        try:
            request = GetItemsRequest(partner_tag=self.tag,
                                      partner_type=PartnerType.ASSOCIATES,
                                      marketplace=marketplace,
                                      item_ids=item_ids,
                                      resources=_resources,
                                      **kwargs)
        except ApiException:
            logger.error("Amazon fetch failed for: %s" % ', '.join(item_ids),
                         exc_info=True)
            return None
        response = self.api.get_items(request)
        products = response.items_result.items
        return (products if not serialize else
                [self.serialize(p) for p in products])


    @staticmethod
    def serialize(product):
        """Takes a full Amazon product Advertising API returned AmazonProduct
        with multiple ResponseGroups, and extracts the data we are
        interested in.

        :param AmazonAPI product:
        :return: Amazon metadata for one product
        :rtype: dict

        {
          'price': '$54.06',
          'price_amt': 5406,
          'physical_format': 'hardcover',
          'authors': [{'name': 'Guterson, David'}],
          'publish_date': 'Jan 21, 2020',
          #'dimensions': {
          #  'width': [1.7, 'Inches'],
          #  'length': [8.5, 'Inches'],
          #  'weight': [5.4, 'Pounds'],
          #  'height': [10.875, 'Inches']
          # },
          'publishers': ['Victory Belt Publishing'],
          'source_records': ['amazon:1628603976'],
          'title': 'Boundless: Upgrade Your Brain, Optimize Your Body & Defy Aging',
          'url': 'https://www.amazon.com/dp/1628603976/?tag=internetarchi-20',
          'number_of_pages': 640,
          'cover': 'https://m.media-amazon.com/images/I/51IT9MV3KqL._AC_.jpg',
          'languages': ['English']
          'edition_num': '1'
        }

        """
        if not product:
            return {}  # no match?

        item_info = getattr(product, 'item_info')
        images = getattr(product, 'images')
        edition_info = item_info and getattr(item_info, 'content_info')
        attribution = item_info and getattr(item_info, 'by_line_info')
        price = (getattr(product, 'offers') and product.offers.listings
                 and product.offers.listings[0].price)
        brand = (attribution and getattr(attribution, 'brand') and
                 getattr(attribution.brand, 'display_value'))
        manufacturer = (
            item_info and
            getattr(item_info, 'by_line_info') and
            getattr(item_info.by_line_info, 'manufacturer') and
            item_info.by_line_info.manufacturer.display_value
        )
        product_group = (
            item_info and
            getattr(item_info, 'classifications',) and
            getattr(item_info.classifications, 'product_group') and
            item_info.classifications.product_group.display_value
        )
        try:
            publish_date = edition_info and isoparser.parse(
                edition_info.publication_date.display_value
            ).strftime('%b %d, %Y')
        except Exception:
            publish_date = None

        book = {
            'url': "https://www.amazon.com/dp/%s/?tag=%s" % (
                product.asin, h.affiliate_id('amazon')),
            'source_records': ['amazon:%s' % product.asin],
            'isbn_10': [product.asin],
            'isbn_13': [isbn_10_to_isbn_13(product.asin)],
            'price': price and price.display_amount,
            'price_amt': price and price.amount and int(100 * price.amount),
            'title': (item_info and item_info.title and
                      getattr(item_info.title, 'display_value')),
            'cover': (images and images.primary and images.primary.large and
                      images.primary.large.url),
            'authors': attribution and [{'name': contrib.name}
                        for contrib in attribution.contributors],
            'publishers': list(set(p for p in (brand, manufacturer) if p)),
            'number_of_pages': (edition_info and edition_info.pages_count and
                                edition_info.pages_count.display_value),
            'edition_num': (edition_info and edition_info.edition and
                            edition_info.edition.display_value),
            'publish_date': publish_date,
            'product_group': product_group,
            'physical_format': (
                item_info and item_info.classifications and
                getattr(item_info.classifications.binding, 'display_value', '').lower()
            ),
        }
        return book


@public
def get_amazon_metadata(id_, id_type='isbn', resources=None):
    """Main interface to Amazon LookupItem API. Will cache results.

    :param str id_: The item id: isbn (10/13), or Amazon ASIN.
    :param str id_type: 'isbn' or 'asin'.
    :return: A single book item's metadata, or None.
    :rtype: dict or None
    """
    return cached_get_amazon_metadata(id_, id_type=id_type, resources=resources)


def search_amazon(title='', author=''):
    """Uses the Amazon Product Advertising API ItemSearch operation to search for
    books by author and/or title.
    https://docs.aws.amazon.com/AWSECommerceService/latest/DG/ItemSearch.html

    XXX! Broken while migrating from paapi 4.0 to 5.0

    :param str title: title of book to search for.
    :param str author: author name of book to search for.
    :return: dict of "results", a list of one or more found books, with metadata.
    :rtype: dict
    """
    pass


def _get_amazon_metadata(id_, id_type='isbn', resources=None):
    """Uses the Amazon Product Advertising API ItemLookup operation to locatate a
    specific book by identifier; either 'isbn' or 'asin'.
    https://docs.aws.amazon.com/AWSECommerceService/latest/DG/ItemLookup.html

    :param str id_: The item id: isbn (10/13), or Amazon ASIN.
    :param str id_type: 'isbn' or 'asin'.
    :return: A single book item's metadata, or None.
    :rtype: dict or None
    """
    if id_type == 'isbn':
        id_ = normalize_isbn(id_)
        if len(id_) == 13 and id_.startswith('978'):
            id_ = isbn_13_to_isbn_10(id_)

    if amazon_api:
        try:
            return amazon_api.get_product(id_, serialize=True, resources=resources)
        except Exception:
            return None


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
        with accounts.RunAs('ImportBot') as account:
            reply = load(
                clean_amazon_metadata_for_load(md), account=account)
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
    response = requests.get(url)
    if response.status_code != requests.codes.ok:
        return {'error': response.text, 'code': response.status_code}
    response = response.content
    new_qty = re.findall("<TotalNew>([0-9]+)</TotalNew>", response)
    new_price = re.findall(r"<LowestNewPrice>\$([0-9.]+)</LowestNewPrice>", response)
    used_price = re.findall(r"<LowestUsedPrice>\$([0-9.]+)</LowestUsedPrice>", response)
    used_qty = re.findall("<TotalUsed>([0-9]+)</TotalUsed>", response)
    market_price = re.findall(r"<LowestMarketPrice>\$([0-9.]+)</LowestMarketPrice>",
                              response)
    price = qlt = None

    if used_qty and used_qty[0] and used_qty[0] != '0':
        price = used_price[0] if used_price else ''
        qlt = 'used'

    if new_qty and new_qty[0] and new_qty[0] != '0':
        _price = new_price[0] if new_price else None
        if _price and (not price or float(_price) < float(price)):
            price = _price
            qlt = 'new'

    market_price = ('$' + market_price[0]) if market_price else None
    return betterworldbooks_fmt(isbn, qlt, price, market_price)


def betterworldbooks_fmt(isbn, qlt=None, price=None, market_price=None):
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
        'market_price': market_price,
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
