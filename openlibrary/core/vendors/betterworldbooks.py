import logging
import re

import requests
from infogami.utils.view import public

from openlibrary.core import cache
from openlibrary.core import helpers as h
from openlibrary.utils import dateutil
from openlibrary.utils.isbn import normalize_isbn

logger = logging.getLogger("openlibrary.vendors.betterworldbooks")

BETTERWORLDBOOKS_API_URL = (
    'https://products.betterworldbooks.com/service.aspx?IncludeAmazon=True&ItemId='
)
BETTERWORLDBOOKS_BASE_URL = 'https://betterworldbooks.com'
BWB_AFFILIATE_LINK = (
    f'http://www.anrdoezrs.net/links/{h.affiliate_id("betterworldbooks")}/type/dlg/'
    'http://www.betterworldbooks.com/-id-%s'
)


@public
def get_betterworldbooks_metadata(isbn: str) -> dict:
    """
    :param str isbn: Unnormalisied ISBN10 or ISBN13
    :return: Metadata for a single BWB book, currently listed on their catalog, or
             an error dict.
    :rtype: dict
    """

    isbn = normalize_isbn(isbn)
    try:
        return _get_betterworldbooks_metadata(isbn)
    except Exception:
        logger.exception(f"_get_betterworldbooks_metadata({isbn})")
        return betterworldbooks_fmt(isbn)


def _get_betterworldbooks_metadata(isbn: str) -> dict:
    """Returns price and other metadata (currently minimal)
    for a book currently available on betterworldbooks.com

    :param str isbn: Normalised ISBN10 or ISBN13
    :return: Metadata for a single BWB book currently listed on their catalog,
            or an error dict.
    :rtype: dict
    """

    url = BETTERWORLDBOOKS_API_URL + isbn
    response = requests.get(url)
    if response.status_code != requests.codes.ok:
        return {'error': response.text, 'code': response.status_code}
    text = response.text
    new_qty = re.findall("<TotalNew>([0-9]+)</TotalNew>", text)
    new_price = re.findall(r"<LowestNewPrice>\$([0-9.]+)</LowestNewPrice>", text)
    used_price = re.findall(r"<LowestUsedPrice>\$([0-9.]+)</LowestUsedPrice>", text)
    used_qty = re.findall("<TotalUsed>([0-9]+)</TotalUsed>", text)
    market_price = re.findall(
        r"<LowestMarketPrice>\$([0-9.]+)</LowestMarketPrice>", text
    )
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


def betterworldbooks_fmt(
    isbn: str,
    qlt: str = None,
    price: str = None,
    market_price: list[str] = None,
) -> dict:
    """Defines a standard interface for returning bwb price info

    :param str isbn:
    :param str qlt: Quality of the book, e.g. "new", "used"
    :param str price: Price of the book as a decimal str, e.g. "4.28"
    :rtype: dict
    """
    price_fmt = f"${price} ({qlt})" if price and qlt else None
    return {
        'url': BWB_AFFILIATE_LINK % isbn,
        'isbn': isbn,
        'market_price': market_price,
        'price': price_fmt,
        'price_amt': price,
        'qlt': qlt,
    }


cached_get_betterworldbooks_metadata = cache.memcache_memoize(
    _get_betterworldbooks_metadata,
    "upstream.code._get_betterworldbooks_metadata",
    timeout=dateutil.HALF_DAY_SECS,
)
