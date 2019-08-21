import json
import urllib
import requests
import web
from infogami import config
from infogami.utils.view import public
from openlibrary import accounts
from openlibrary.core import models
from openlibrary.core.lending import get_work_availability, config_ia_domain
from openlibrary.core.vendors import (
    get_betterworldbooks_metadata, create_edition_from_amazon_metadata)
from openlibrary.accounts import get_internet_archive_id
from openlibrary.core.lending import config_ia_civicrm_api
from openlibrary.utils.isbn import to_isbn_13

try:
    from booklending_utils.sponsorship import eligibility_check
except ImportError:
    def eligibility_check(edition):
        """For testing if Internet Archive book sponsorship check unavailable"""
        work = edition.works[0]
        authors = [w.author.name for w in work.authors]
        if authors:
            return True

CIVI_ISBN = 'custom_52'
CIVI_USERNAME = 'custom_51'
CIVI_CONTEXT = 'custom_53'
PRICE_LIMIT_CENTS = 5000


def get_sponsored_editions(user):
    """
    Gets a list of books from the civi API which internet archive
    @archive_username has sponsored
    """
    archive_id = get_internet_archive_id(user.key if 'key' in user else user._key)
    contact_id = get_contact_id_by_username(archive_id)
    return contact_id and get_sponsorships_by_contact_id(contact_id)


def get_contact_id_by_username(username):
    """TODO: Use CiviCRM Explorer to replace with call to get contact_id by username"""
    data = {
        'entity': 'Contact',
        'action': 'get',
        'api_key': config_ia_civicrm_api.get('api_key', ''),
        'key': config_ia_civicrm_api.get('site_key', ''),
        'json': {
            "sequential": 1,
            CIVI_USERNAME: username
        }
    }
    data['json'] = json.dumps(data['json'])  # flatten the json field as a string
    r = requests.get(
        config_ia_civicrm_api.get('url', ''),
        params=urllib.urlencode(data),
        headers={
            'Authorization': 'Basic %s' % config_ia_civicrm_api.get('auth', '')
        })
    contacts = r.json().get('values', None)
    return contacts and contacts[0].get('contact_id')


def get_sponsorships_by_contact_id(contact_id, isbn=None):
    data = {
        'entity': 'Contribution',
        'action': 'get',
        'api_key': config_ia_civicrm_api.get('api_key', ''),
        'key': config_ia_civicrm_api.get('site_key', ''),
        'json': {
            "sequential": 1,
            "financial_type_id": "Book Sponsorship",
            "contact_id": contact_id
        }
    }
    if isbn:
        data['json'][CIVI_ISBN] = isbn
    data['json'] = json.dumps(data['json'])  # flatten the json field as a string
    r = requests.get(
        config_ia_civicrm_api.get('url', ''),
        params=urllib.urlencode(data),
        headers={
            'Authorization': 'Basic %s' % config_ia_civicrm_api.get('auth', '')
        })
    txs = r.json().get('values')
    return [{
        'isbn': t.pop(CIVI_ISBN),
        'context': t.pop(CIVI_CONTEXT),
        'receive_date': t.pop('receive_date'),
        'total_amount': t.pop('total_amount')
    } for t in txs]


def isbn_qualifies_for_sponsorship(isbn):
    """Checks possible isbn10 + isbn13 variations to"""
    edition = models.Edition.get_by_isbn(isbn)
    if edition:
        return qualifies_for_sponsorship(edition)

@public
def qualifies_for_sponsorship(edition):
    # defaults
    dwhi = None
    eligibility = False
    price = None

    work = edition.works and edition.works[0]
    edition.isbn13 = to_isbn_13(edition.isbn_13 and edition.isbn_13[0] or
                              edition.isbn_10 and edition.isbn_10[0])
    req_fields = all(edition.get(x) for x in [
        'publishers', 'title', 'publish_date', 'covers',
        'number_of_pages', 'isbn13'
    ])
    if not (work and req_fields and edition.isbn13):
        return {
            'do_we_have_it': dwhi,
            'is_eligibile': eligibility,
            'price': price,
            'error': ("Open Library is missing book metadata "
                      "necessary for sponsorship"),
        }

    work_id = work.key.split("/")[-1]
    num_pages = int(edition.get('number_of_pages'))
    availability = get_work_availability(work_id)
    dwhi = (availability.get(work_id, {}).get('status', 'error') != 'error') and availability
    if not dwhi:
        bwb_price = get_betterworldbooks_metadata(
            edition.isbn13).get('price_amt')
        if bwb_price:
            SETUP_COST_CENTS = 300
            PAGE_COST_CENTS = 12
            scan_price_cents = SETUP_COST_CENTS + (PAGE_COST_CENTS * num_pages)
            book_cost_cents = int(float(bwb_price) * 100)
            total_price_cents = scan_price_cents + book_cost_cents
            price = {
                'book_cost_cents': book_cost_cents,
                'scan_price_cents': scan_price_cents,
                'total_price_cents': total_price_cents
            }
            if total_price_cents <= PRICE_LIMIT_CENTS:
                eligibility = eligibility_check(edition)
    params = {
        'campaign': 'pilot',
        'type': 'sponsorship',
        'context': 'ol',
        'isbn': edition.isbn13
    }
    return {
        'is_eligible': eligibility,
        'do_we_have_it': dwhi,
        'price': price,
        'url': config_ia_domain + '/donate?' + urllib.urlencode(params)
    }


def get_all_sponsors():
    """TODO: Query civi for a list of all sponsorships, for all users. These
    results will have to be summed by user for the leader-board and
    then cached
    """
    pass
