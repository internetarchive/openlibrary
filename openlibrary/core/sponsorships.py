import requests
from infogami import config
from infogami.utils.view import public
from openlibrary import accounts
from openlibrary.core.lending import get_work_availability
from openlibrary.core.vendors import get_betterworldbooks_metadata

PRICE_LIMIT = 50.00
CIVI_SPONSOR_API = '%s/internal/fake/civicrm' % config.get('servername', 'http://localhost')

def get_all_sponsors():
    """
    Query civi for a list of all sponsorships, for all users.
    These results will have to be summed by user for the
    leader-board and then cached
    """
    pass  # todo, later

def get_sponsored_editions(archive_username, limit=50, offset=0):
    """
    Gets a list of books from the civi API which internet archive 
    @archive_username has sponsored
    """
    return requests.get(CIVI_SPONSOR_API).json()["works"]

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
           



        
