import json
import logging
import requests
import web

from urllib.parse import urlencode

from collections import OrderedDict
from infogami.utils.view import public
from openlibrary.core import lending
from openlibrary.core.vendors import get_betterworldbooks_metadata, get_amazon_metadata
from openlibrary import accounts
from openlibrary.accounts.model import get_internet_archive_id, sendmail
from openlibrary.core.civicrm import (
    get_contact_id_by_username,
    get_sponsorships_by_contact_id,
    get_sponsorship_by_isbn,
)
import internetarchive as ia

try:
    from booklending_utils.sponsorship import eligibility_check, BLOCKED_PATRONS
except ImportError:
    BLOCKED_PATRONS = []

    def eligibility_check(edition, patron=None):
        """For testing if Internet Archive book sponsorship check unavailable"""
        return False


logger = logging.getLogger("openlibrary.sponsorship")
SETUP_COST_CENTS = 300
PAGE_COST_CENTS = 12


def get_sponsored_editions_civi(user):
    """
    Deprecated by get_sponsored_editions but worth maintaining as we
    may periodically have to programmatically access data from civi
    since it is the ground-truth of this data.

    Gets a list of books from the civi API which internet archive
    @archive_username has sponsored

    :param user user: infogami user
    :rtype: list
    :return: list of archive.org items sponsored by user
    """
    archive_id = get_internet_archive_id(user.key if 'key' in user else user._key)
    # MyBooks page breaking on local environments without archive_id check
    if archive_id:
        contact_id = get_contact_id_by_username(archive_id) if archive_id else None
        return get_sponsorships_by_contact_id(contact_id) if contact_id else []
    return []


def get_sponsored_editions(user, page=1):
    """
    Gets a list of books from archive.org elasticsearch
    @archive_username has sponsored

    :param user user: infogami user
    :rtype: list
    :return: list of archive.org editions sponsored by user
    """
    archive_id = get_internet_archive_id(user.key if 'key' in user else user._key)
    if archive_id:
        url = 'https://archive.org/advancedsearch.php'
        params = urlencode({
            'fl[]': ['identifier', 'openlibrary_edition'],
            'sort[]': 'date',
            'output': 'json',
            'page': page,
            'rows': 50,
            'q': f'donor:{archive_id}'
        }, doseq=True)
        r = requests.get(f'{url}?{params}')
        # e.g. [{'openlibrary_edition': 'OL24896084M', 'identifier': 'isbn_9780691160191'}]
        return r.json()['response'].get('docs')
    return []


def do_we_want_it(isbn):
    """
    Returns True if we don't have this edition (or other editions of
    the same work), if the isbn has not been promised to us, has not
    yet been sponsored, and is not already in our possession.

    :param str isbn: isbn10 or isbn13
    :param str work_id: e.g. OL123W
    :rtype: (bool, list)
    :return: bool answer to do-we-want-it, list of matching books
    """
    # We don't have any of these work's editions available to borrow
    # Let's confirm this edition hasn't already been sponsored or promised
    params = {
        'search_field': 'isbn',
        'include_promises': 'true',  # include promises and sponsored books
        'search_id': isbn,
    }
    url = '%s/book/marc/ol_dedupe.php' % lending.config_ia_domain
    try:
        data = requests.get(url, params=params).json()
        dwwi = data.get('response', 0)
        return dwwi == 1, data.get('books', [])
    except:
        logger.error("DWWI Failed for isbn %s" % isbn, exc_info=True)
    # err on the side of false negative
    return False, []


@public
def qualifies_for_sponsorship(edition, scan_only=False, donate_only=False, patron=None):
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
        "title": "Lords of the Ring",
        "isbn": "9780299204204"
        "openlibrary_edition": "OL2347684M",
        "openlibrary_work": "OL10317216W"
       },
       "price": {
          "scan_price_cents": 3444,
          "book_cost_cents": 298,
          "total_price_display": "$37.42",
          "total_price_cents": 3742
        },
       "is_eligible": True,
       "sponsor_url": "https://archive.org/donate?isbn=9780299204204&type=sponsorship&context=ol&campaign=pilot"
    }
    """
    resp = {'is_eligible': False, 'price': None}

    edition.isbn = edition.get_isbn13()
    edition.cover = edition.get('covers') and (
        'https://covers.openlibrary.org/b/id/%s-L.jpg' % edition.covers[0]
    )
    amz_metadata = edition.isbn and get_amazon_metadata(edition.isbn) or {}
    req_fields = [
        'isbn',
        'publishers',
        'title',
        'publish_date',
        'cover',
        'number_of_pages',
    ]
    edition_data = {
        field: (amz_metadata.get(field) or edition.get(field)) for field in req_fields
    }
    work = edition.works and edition.works[0]

    if not (work and all(edition_data.values())):
        resp['error'] = {
            'reason': 'Open Library is missing book metadata necessary for sponsorship',
            'values': edition_data,
        }
        return resp

    work_id = edition.works[0].key.split("/")[-1]
    edition_id = edition.key.split('/')[-1]
    dwwi, matches = do_we_want_it(edition.isbn)
    if dwwi:
        num_pages = int(edition_data['number_of_pages'])
        bwb_price = None
        if not donate_only:
            if not scan_only:
                bwb_price = get_betterworldbooks_metadata(edition.isbn).get('price_amt')
            if scan_only or bwb_price:
                scan_price_cents = SETUP_COST_CENTS + (PAGE_COST_CENTS * num_pages)
                book_cost_cents = int(float(bwb_price) * 100) if not scan_only else 0
                total_price_cents = scan_price_cents + book_cost_cents
                resp['price'] = {
                    'book_cost_cents': book_cost_cents,
                    'scan_price_cents': scan_price_cents,
                    'total_price_cents': total_price_cents,
                    'total_price_display': f'${total_price_cents / 100.0:,.2f}',
                }
        if donate_only or scan_only or bwb_price:
            resp['is_eligible'] = eligibility_check(edition, patron=patron)
    else:
        resp['error'] = {'reason': 'matches', 'values': matches}
    edition_data.update(
        {'openlibrary_edition': edition_id, 'openlibrary_work': work_id}
    )
    resp.update(
        {
            'edition': edition_data,
            'sponsor_url': 'https://openlibrary.org/bookdrive',
        }
    )
    return resp


def sync_completed_sponsored_books(dryrun=False):
    """Retrieves a list of all completed sponsored books from Archive.org
    so they can be synced with Open Library, which entails:

    - adding IA ocaid into openlibrary edition
    - alerting patrons (if possible) by email of completion
    - possibly marking archive.org item status as complete/synced

    XXX Note: This `search_items` query requires the `ia` tool (the
    one installed via virtualenv) to be configured with (scope:all)
    privileged s3 keys.
    """
    items = ia.search_items(
        'collection:openlibraryscanningteam AND collection:inlibrary',
        fields=['identifier', 'openlibrary_edition'],
        params={'page': 1, 'rows': 1000, 'scope': 'all'},
        config={'general': {'secure': False}},
    )
    books = web.ctx.site.get_many(
        [
            '/books/%s' % i.get('openlibrary_edition')
            for i in items
            if i.get('openlibrary_edition')
        ]
    )
    unsynced = [book for book in books if not book.ocaid]
    ocaid_lookup = {
        '/books/%s' % i.get('openlibrary_edition'): i.get('identifier') for i in items
    }
    fixed = []
    for book in unsynced:
        book.ocaid = ocaid_lookup[book.key]
        with accounts.RunAs('ImportBot'):
            if not dryrun:
                web.ctx.site.save(book.dict(), "Adding ocaid for completed sponsorship")
            fixed.append({'key': book.key, 'ocaid': book.ocaid})
            # TODO: send out an email?... Requires Civi.
            if book.ocaid.startswith("isbn_"):
                isbn = book.ocaid.split("_")[-1]
                sponsorship = get_sponsorship_by_isbn(isbn)
                contact = sponsorship and sponsorship.get("contact")
                email = contact and contact.get("email")
                if not dryrun and email:
                    email_sponsor(email, book)
    return json.dumps(fixed)


def email_sponsor(recipient, book, bcc="mek@archive.org"):
    url = 'https://openlibrary.org%s' % book.key
    resp = web.sendmail(
        "openlibrary@archive.org",
        recipient,
        "Internet Archive: Your Open Library Book Sponsorship is Ready",
        (
            '<p>'
            + f'<a href="{url}">{book.title}</a> '
            + 'is now available to read on Open Library!'
            + '</p>'
            + '<p>Thank you,</p>'
            + '<p>The <a href="https://openlibrary.org">Open Library</a> Team</p>'
        ),
        bcc=bcc,
        headers={'Content-Type': 'text/html;charset=utf-8'},
    )
    return resp


def get_sponsored_books():
    """Performs the `ia` query to fetch sponsored books from archive.org"""
    # XXX Note: This `search_items` query requires the `ia` tool (the
    # one installed via virtualenv) to be configured with (scope:all)
    # privileged s3 keys.
    items = ia.search_items(
        'collection:openlibraryscanningteam',
        fields=[
            'identifier',
            'est_book_price',
            'est_scan_price',
            'scan_price',
            'book_price',
            'repub_state',
            'imagecount',
            'title',
            'donor',
            'openlibrary_edition',
            'publicdate',
            'collection',
            'isbn',
        ],
        params={'page': 1, 'rows': 1000},
        config={'general': {'secure': False}},
    )
    return [
        item
        for item in items
        if not (
            item.get('repub_state') == '-1' and item.get('donor') in BLOCKED_PATRONS
        )
    ]


def summary():
    """
    Provides data model (finances, state-of-process) for the /admin/sponsorship stats
    page.

    Screenshot:
    https://user-images.githubusercontent.com/978325/71494377-b975c880-27fb-11ea-9c95-c0c1bfa78bda.png
    """
    items = list(get_sponsored_books())

    # Construct a map of each state of the process to a count of books in that state
    STATUSES = [
        'Needs purchasing',
        'Needs digitizing',
        'Needs republishing',
        'Complete',
    ]
    status_counts = OrderedDict((status, 0) for status in STATUSES)
    for book in items:
        # Official sponsored items set repub_state -1 at item creation,
        # bulk sponsorship (item created at time of scanning by ttscribe)
        # will not be repub_state -1. Thus. books which have repub_state -1
        # and no price are those we need to digitize:
        if int(book.get('repub_state', -1)) == -1 and not book.get('book_price'):
            book['status'] = STATUSES[0]
            status_counts[STATUSES[0]] += 1
        elif int(book.get('repub_state', -1)) == -1:
            book['status'] = STATUSES[1]
            status_counts[STATUSES[1]] += 1
        elif int(book.get('repub_state', 0)) < 14:
            book['status'] = STATUSES[2]
            status_counts[STATUSES[2]] += 1
        else:
            book['status'] = STATUSES[3]
            status_counts[STATUSES[3]] += 1

    total_pages_scanned = sum(int(i.get('imagecount', 0)) for i in items)
    total_unscanned_books = len([i for i in items if not i.get('imagecount', 0)])
    total_cost_cents = sum(
        int(i.get('est_book_price', 0)) + int(i.get('est_scan_price', 0)) for i in items
    )
    book_cost_cents = sum(int(i.get('book_price', 0)) for i in items)
    est_book_cost_cents = sum(int(i.get('est_book_price', 0)) for i in items)
    scan_cost_cents = (PAGE_COST_CENTS * total_pages_scanned) + (
        SETUP_COST_CENTS * len(items)
    )
    est_scan_cost_cents = sum(int(i.get('est_scan_price', 0)) for i in items)
    avg_scan_cost = scan_cost_cents / (len(items) - total_unscanned_books)

    return {
        'books': items,
        'status_ids': {name: i for i, name in enumerate(STATUSES)},
        'status_counts': status_counts,
        'total_pages_scanned': total_pages_scanned,
        'total_unscanned_books': total_unscanned_books,
        'total_cost_cents': total_cost_cents,
        'book_cost_cents': book_cost_cents,
        'est_book_cost_cents': est_book_cost_cents,
        'delta_book_cost_cents': est_book_cost_cents - book_cost_cents,
        'scan_cost_cents': scan_cost_cents,
        'est_scan_cost_cents': est_scan_cost_cents,
        'delta_scan_cost_cents': est_scan_cost_cents - scan_cost_cents,
        'avg_scan_cost': avg_scan_cost,
    }
