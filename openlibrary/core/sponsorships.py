import json
import urllib
import requests
from infogami import config
from infogami.utils.view import public
from openlibrary import accounts
from openlibrary.core.lending import get_work_availability
from openlibrary.core.vendors import get_betterworldbooks_metadata
from openlibrary.accounts import get_internet_archive_id

CIVI_SPONSOR_API = config.get('plugin_civicrm')
CIVI_URL = CIVI_SPONSOR_API.get('url')
CIVI_HEADERS = {'Authorization': 'Basic %s' % CIVI_SPONSOR_API.get('auth', '')}
CIVI_ISBN = 'custom_52'
CIVI_USERNAME = 'custom_51'
CIVI_CONTEXT = 'custom_53'
PRICE_LIMIT = 50.00


def get_sponsored_editions(user):
    """
    Gets a list of books from the civi API which internet archive
    @archive_username has sponsored
    """
    archive_id = get_internet_archive_id(user.key if 'key' in user else user._key)
    contact_id = get_contact_id_by_username(archive_id)
    return contact_id and {
        'username': archive_id,
        'sponsorships': get_sponsorships_by_contact_id(contact_id)
    }


def get_contact_id_by_username(username):
    """TODO: Use CiviCRM Explorer to replace with call to get contact_id by username"""
    data = {
        'entity': 'Contact',
        'action': 'get',
        'api_key': CIVI_SPONSOR_API.get('api_key', ''),
        'key': CIVI_SPONSOR_API.get('site_key', ''),
        'json': {
            "sequential": 1,
            CIVI_USERNAME: username
        }
    }
    data['json'] = json.dumps(data['json'])  # flatten the json field as a string
    r = requests.get(CIVI_URL, params=urllib.urlencode(data), headers=CIVI_HEADERS)
    contacts = r.json().get('values', None)
    return contacts and contacts[0].get('contact_id')


def get_sponsorships_by_contact_id(contact_id, isbn=None):
    data = {
        'entity': 'Contribution',
        'action': 'get',
        'api_key': CIVI_SPONSOR_API.get('api_key', ''),
        'key': CIVI_SPONSOR_API.get('site_key', ''),
        'json': {
            "sequential": 1,
            "financial_type_id": "Book Sponsorship",
            "contact_id": contact_id
        }
    }
    if isbn:
        data['json'][CIVI_ISBN] = isbn
    data['json'] = json.dumps(data['json'])  # flatten the json field as a string
    r = requests.get(CIVI_URL, params=urllib.urlencode(data), headers=CIVI_HEADERS)
    txs = r.json().get('values')
    return [{
        'isbn': t.pop(CIVI_ISBN),
        'context': t.pop(CIVI_CONTEXT),
        'receive_date': t.pop('receive_date'),
        'total_amount': t.pop('total_amount')
    } for t in txs]


@public
def qualifies_for_sponsorship(edition):
    # User must be logged in and in /usergroup/sponsors list
    work = edition.works and edition.works[0]
    req_fields = all(edition.get(x) for x in [
        'publishers', 'title', 'publish_date', 'covers', 'number_of_pages'
    ])
    isbn = (edition.isbn_13 and edition.isbn_13[0] or
             edition.isbn_10 and edition.isbn_10[0])
    if work and req_fields and isbn:
        work_id = work.key.split("/")[-1]
        num_pages = int(edition.get('number_of_pages'))
        availability = get_work_availability(work_id)
        dwwi = availability.get(work_id, {}).get('status', 'error') == 'error'
        if dwwi:
            bwb_price = get_betterworldbooks_metadata(isbn).get('price_amt')
            scan_price = 3.0 + (.12 * num_pages)
            total_price = scan_price + float(bwb_price)
            return total_price <= PRICE_LIMIT
    return False


def get_all_sponsors():
    """TODO: Query civi for a list of all sponsorships, for all users. These
    results will have to be summed by user for the leader-board and
    then cached
    """
    pass
