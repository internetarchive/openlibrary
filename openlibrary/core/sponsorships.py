import urllib
import requests
import logging
from infogami import config
from infogami.utils.view import public
from openlibrary.core import models
from openlibrary.core.lending import (
    get_work_availability, config_ia_domain)
from openlibrary.core.vendors import (
    get_betterworldbooks_metadata,
    get_amazon_metadata)
from openlibrary.accounts.model import get_internet_archive_id
from openlibrary.core.civicrm import (
    get_contact_id_by_username,
    get_sponsorships_by_contact_id)
from openlibrary.utils.isbn import to_isbn_13
try:
    from booklending_utils.sponsorship import eligibility_check
except ImportError:
    def eligibility_check(edition):
        """For testing if Internet Archive book sponsorship check unavailable"""
        return False

logger = logging.getLogger("openlibrary.sponsorship")


def get_sponsored_editions(user):
    """
    Gets a list of books from the civi API which internet archive
    @archive_username has sponsored

    :param user user: infogami user
    :rtype: list
    :return: list of editions sponsored by user
    """
    archive_id = get_internet_archive_id(user.key if 'key' in user else user._key)
    contact_id = get_contact_id_by_username(archive_id)
    return get_sponsorships_by_contact_id(contact_id) if contact_id else []


def do_we_want_it(isbn, work_id):
    """
    Returns True if we don't have this edition (or other editions of
    the same work), if the isbn has not been promised to us, has not
    yet been sponsored, and is not already in our possession.

    :param str isbn: isbn10 or isbn13
    :param str work_id: e.g. OL123W
    :rtype: (bool, list)
    :return: bool answer to do-we-want-it, list of matching books
    """
    availability = get_work_availability(work_id)  # checks all editions
    if availability and availability.get(work_id, {}).get('status', 'error') != 'error':
        return False, availability

    # We don't have any of these work's editions available to borrow
    # Let's confirm this edition hasn't already been sponsored or promised
    params = {
        'search_field': 'isbn',
        'include_promises': 'true',  # include promises and sponsored books
        'search_id': isbn
    }
    url = '%s/book/marc/ol_dedupe.php?%s' % (config_ia_domain,  urllib.urlencode(params))
    r = requests.get(url)
    try:
        data = r.json()
        dwwi = data.get('response', 0)
        return dwwi==1, data.get('books', [])
    except:
        logger.error("DWWI Failed for isbn %s" % isbn, exc_info=True)
    # err on the side of false negative
    return False, []

@public
def qualifies_for_sponsorship(edition):
    """
    :param edition edition: An infogami book edition
    :rtype: dict
    :return: A dict with book eligibility:
    {
     "edition": {
        "publishers": ["University of Wisconsin Press"],
        "number_of_pages": 262,
        "publish_date": "September 22, 2004",
        "cover": "https://covers.openlibrary.org/b/id/2353907-L.jpg",
        "title": "Lords of the Ring"
       },
       "price": {
          "scan_price_cents": 3444,
          "book_cost_cents": 298,
          "total_price_display": "$37.42",
          "total_price_cents": 3742
        },
       "is_eligible": true,
       "sponsor_url": "https://archive.org/donate?isbn=9780299204204&type=sponsorship&context=ol&campaign=pilot"
    }
    """
    resp = {
        'is_eligible': False,
        'price': None
    }

    edition.isbn13 = edition.get_isbn13()
    edition.cover = edition.get('covers') and (
        'https://covers.openlibrary.org/b/id/%s-L.jpg' % edition.covers[0])

    if not edition.isbn13:
        resp['error'] = {
            'reason': 'Missing ISBN',
        }

    amz_metadata = get_amazon_metadata(edition.isbn13) or {}
    req_fields = ['publishers', 'title', 'publish_date', 'cover', 'number_of_pages']
    edition_data = dict((field, (edition.get(field) or amz_metadata.get(field))) for field in req_fields)
    work = edition.works and edition.works[0]
    if not (work and all(edition_data.values())):
        resp['error'] = {
            'reason': 'Open Library is missing book metadata necessary for sponsorship',
            'values': edition_data
        }
        return resp

    work_id = work.key.split("/")[-1]
    dwwi, matches = do_we_want_it(edition.isbn13, work_id)
    if dwwi:
        bwb_price = get_betterworldbooks_metadata(
            edition.isbn13).get('price_amt')
        if bwb_price:
            SETUP_COST_CENTS = 300
            PAGE_COST_CENTS = 12
            num_pages = int(edition_data['number_of_pages'])
            scan_price_cents = SETUP_COST_CENTS + (PAGE_COST_CENTS * num_pages)
            book_cost_cents = int(float(bwb_price) * 100)
            total_price_cents = scan_price_cents + book_cost_cents
            resp['price'] = {
                'book_cost_cents': book_cost_cents,
                'scan_price_cents': scan_price_cents,
                'total_price_cents': total_price_cents,
                'total_price_display': '${:,.2f}'.format(
                    total_price_cents / 100.
                ),
            }
            resp['is_eligible'] = eligibility_check(edition)
    else:
        resp['error'] = {
            'reason': 'matches',
            'values': matches
        }
    resp.update({
        'edition': edition_data,
        'sponsor_url': config_ia_domain + '/donate?' + urllib.urlencode({
            'campaign': 'pilot',
            'type': 'sponsorship',
            'context': 'ol',
            'isbn': edition.isbn13
        })
    })
    return resp
