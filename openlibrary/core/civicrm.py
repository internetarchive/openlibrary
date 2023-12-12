import json
import logging

import requests

from openlibrary.core import lending

CIVI_ISBN = 'custom_52'
CIVI_USERNAME = 'custom_51'
CIVI_CONTEXT = 'custom_53'
logger = logging.getLogger("openlibrary.civicrm")


def get_contact(username=None, contact_id=None):
    if not (contact_id or username):
        raise Exception("contact_id and or username required")
    data = {
        "entity": "Contact",
        "action": "get",
        "api_key": lending.config_ia_civicrm_api.get("api_key", ""),
        "key": lending.config_ia_civicrm_api.get("site_key", ""),
        "json": {
            "sequential": 1,
        },
    }
    if username:
        data["json"][CIVI_USERNAME] = username
    if contact_id:
        data["json"]["contact_id"] = contact_id
    data["json"] = json.dumps(data["json"])  # flatten the json field as a string
    try:
        r = requests.get(
            lending.config_ia_civicrm_api.get("url", ""),
            params=data,
            timeout=3,
            headers=dict(
                Authorization=f"Basic {lending.config_ia_civicrm_api.get('auth', '')}"
            ),
        )
        contacts = r.status_code == 200 and r.json().get("values", None)
        return contacts and contacts[0]
    except requests.Timeout:
        logger.error('Timeout accessing CiviCRM')

    return None


def get_contact_id_by_username(username):
    """TODO: Use CiviCRM Explorer to replace with call to get contact_id by username"""
    contact = get_contact(username=username)
    return contact and contact.get("contact_id")


def get_sponsorship_by_isbn(isbn):
    sponsorship = get_sponsorships_by_contact_id(isbn=isbn)
    sponsorship = sponsorship and sponsorship[0]
    if sponsorship:
        contact_id = sponsorship.get("contact_id")
        sponsorship['contact'] = get_contact(contact_id=contact_id)
    return sponsorship


def get_sponsorships_by_contact_id(contact_id=None, isbn=None):
    if not (contact_id or isbn):
        raise Exception("contact_id and or isbn required")
    data = {
        "entity": "Contribution",
        "action": "get",
        "api_key": lending.config_ia_civicrm_api.get("api_key", ""),
        "key": lending.config_ia_civicrm_api.get("site_key", ""),
        "json": {
            "sequential": 1,
            "financial_type_id": "Book Sponsorship",
        },
    }
    if contact_id:
        data["json"]["contact_id"] = contact_id
    if isbn:
        data["json"][CIVI_ISBN] = isbn
    data["json"] = json.dumps(data["json"])  # flatten the json field as a string
    try:
        txs = (
            requests.get(
                lending.config_ia_civicrm_api.get("url", ""),
                timeout=3,
                params=data,
                headers=dict(
                    Authorization=f"Basic {lending.config_ia_civicrm_api.get('auth', '')}"
                ),
            )
            .json()
            .get("values")
        )
        return [
            {
                "isbn": t.pop(CIVI_ISBN),
                "context": t.pop(CIVI_CONTEXT),
                "receive_date": t.pop("receive_date"),
                "total_amount": t.pop("total_amount"),
                "contact_id": t.pop("contact_id"),
                "contribution_status": t.pop("contribution_status"),
            }
            for t in txs
        ]
    except requests.Timeout:
        logger.error('Timeout accessing CiviCRM')

    return []
