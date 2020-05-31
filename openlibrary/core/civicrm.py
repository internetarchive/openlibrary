import json
import requests

from infogami import config
from openlibrary.core import lending 

CIVI_ISBN = 'custom_52'
CIVI_USERNAME = 'custom_51'
CIVI_CONTEXT = 'custom_53'


def get_contact_id_by_username(username):
    """TODO: Use CiviCRM Explorer to replace with call to get contact_id by username"""
    data = {
        'entity': 'Contact',
        'action': 'get',
        'api_key': lending.config_ia_civicrm_api.get('api_key', ''),
        'key': lending.config_ia_civicrm_api.get('site_key', ''),
        'json': {
            "sequential": 1,
            CIVI_USERNAME: username
        }
    }
    data['json'] = json.dumps(data['json'])  # flatten the json field as a string
    r = requests.get(
        lending.config_ia_civicrm_api.get('url', ''),
        params=data,
        headers={
            'Authorization': 'Basic %s' % lending.config_ia_civicrm_api.get('auth', '')
        })
    contacts = r.status_code == 200 and r.json().get('values', None)
    return contacts and contacts[0].get('contact_id')


def get_sponsorships_by_contact_id(contact_id, isbn=None):
    data = {
        'entity': 'Contribution',
        'action': 'get',
        'api_key': lending.config_ia_civicrm_api.get('api_key', ''),
        'key': lending.config_ia_civicrm_api.get('site_key', ''),
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
        lending.config_ia_civicrm_api.get('url', ''),
        params=data,
        headers={
            'Authorization': 'Basic %s' % lending.config_ia_civicrm_api.get('auth', '')
        })
    txs = r.json().get('values')
    return [{
        'isbn': t.pop(CIVI_ISBN),
        'context': t.pop(CIVI_CONTEXT),
        'receive_date': t.pop('receive_date'),
        'total_amount': t.pop('total_amount')
    } for t in txs]
