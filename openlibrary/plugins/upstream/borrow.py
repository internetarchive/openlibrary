"""Handlers for borrowing books"""

import copy
import hashlib
import hmac
import json
import logging
import re
import time
import urllib
from datetime import datetime
from typing import Literal

import lxml.etree
import web
from lxml import etree

from infogami import config
from infogami.infobase.utils import parse_datetime
from infogami.utils import delegate
from infogami.utils.view import (
    add_flash_message,
    public,
)
from openlibrary import accounts
from openlibrary.accounts.model import OpenLibraryAccount
from openlibrary.app import render_template
from openlibrary.core import (
    lending,
    models,  # noqa: F401 side effects may be needed
    stats,
    vendors,
    waitinglist,
)
from openlibrary.i18n import gettext as _
from openlibrary.utils import dateutil

logger = logging.getLogger("openlibrary.borrow")

# ######### Constants

lending_library_subject = 'Lending library'
in_library_subject = 'In library'
lending_subjects = {lending_library_subject, in_library_subject}

# Max loans a user can have at once
user_max_loans = 5

# When we generate a loan offer (.acsm) for a user we assume that the loan has occurred.
# Once the loan fulfillment inside Digital Editions the book status server will know
# the loan has occurred.  We allow this timeout so that we don't delete the OL loan
# record before fulfillment because we can't find it in the book status server.
# $$$ If a user borrows an ACS4 book and immediately returns book loan will show as
#     "not yet downloaded" for the duration of the timeout.
#     BookReader loan status is always current.
loan_fulfillment_timeout_seconds = 60 * 5

# How long the auth token given to the BookReader should last.  After the auth token
# expires the BookReader will not be able to access the book.  The BookReader polls
# OL periodically to get fresh tokens.
BOOKREADER_AUTH_SECONDS = dateutil.MINUTE_SECS * 10
READER_AUTH_SECONDS = dateutil.MINUTE_SECS * 2

# Base URL for BookReader
try:
    bookreader_host = config.bookreader_host  # type: ignore[attr-defined]
except AttributeError:
    bookreader_host = 'archive.org'

bookreader_stream_base = f'https://{bookreader_host}/stream'


# ######### Page Handlers


# Handler for /books/{bookid}/{title}/borrow
class checkout_with_ocaid(delegate.page):
    path = "/borrow/ia/(.*)"

    def GET(self, ocaid):
        """Redirect shim: Translate an IA identifier into an OL identifier and
        then redirects user to the canonical OL borrow page.
        """
        i = web.input()
        params = urllib.parse.urlencode(i)
        ia_edition = web.ctx.site.get('/books/ia:%s' % ocaid)
        if not ia_edition:
            raise web.notfound()
        edition = web.ctx.site.get(ia_edition.location)
        url = '%s/x/borrow' % edition.key
        raise web.seeother(url + '?' + params)

    def POST(self, ocaid):
        """Redirect shim: Translate an IA identifier into an OL identifier and
        then forwards a borrow request to the canonical borrow
        endpoint with this OL identifier.
        """
        ia_edition = web.ctx.site.get('/books/ia:%s' % ocaid)
        if not ia_edition:
            raise web.notfound()
        borrow().POST(ia_edition.location)


# Handler for /books/{bookid}/{title}/borrow
class borrow(delegate.page):
    path = "(/books/.*)/borrow"

    def GET(self, key):
        return self.POST(key)

    def POST(self, key):  # noqa: PLR0915
        """Called when the user wants to borrow the edition"""

        i = web.input(
            action='borrow',
            format=None,
            _autoReadAloud=None,
            q="",
            redirect="",
        )

        action = i.action
        edition = web.ctx.site.get(key)
        if not edition:
            raise web.notfound()

        from openlibrary.book_providers import get_book_provider  # noqa: PLC0415

        if action == 'locate':
            raise web.seeother(edition.get_worldcat_url())

        # Direct to the first web book if at least one is available.
        if (
            action in ["borrow", "read"]
            and (provider := get_book_provider(edition))
            and provider.short_name != "ia"
            and (acquisitions := provider.get_acquisitions(edition))
            and acquisitions[0].access == "open-access"
        ):
            stats.increment('ol.loans.webbook')
            return render_template(
                "interstitial",
                url=acquisitions[0].url,
                provider_name=acquisitions[0].provider_name,
            )

        archive_url = get_bookreader_stream_url(edition.ocaid) + '?ref=ol'
        if i._autoReadAloud is not None:
            archive_url += '&_autoReadAloud=show'

        if i.q:
            _q = urllib.parse.quote(i.q, safe='')
            raise web.seeother(archive_url + "#page/-/mode/2up/search/%s" % _q)

        # Make a call to availability v2 update the subjects according
        # to result if `open`, redirect to bookreader
        response = lending.get_availability('identifier', [edition.ocaid])
        availability = response[edition.ocaid] if response else {}
        if availability and availability['status'] == 'open':
            from openlibrary.plugins.openlibrary.code import is_bot  # noqa: PLC0415

            if not is_bot():
                stats.increment('ol.loans.openaccess')
            raise web.seeother(archive_url)

        error_redirect = archive_url
        edition_redirect = urllib.parse.quote(i.redirect or edition.url())
        user = accounts.get_current_user()

        if user:
            account = OpenLibraryAccount.get_by_email(user.email)
            ia_itemname = account.itemname if account else None
            s3_keys = web.ctx.site.store.get(account._key).get('s3_keys')
            lending.get_cached_loans_of_user.memcache_delete(
                user.key, {}
            )  # invalidate cache for user loans
        if not user or not ia_itemname or not s3_keys:
            web.setcookie(config.login_cookie_name, "", expires=-1)
            redirect_url = (
                f"/account/login?redirect={edition_redirect}/borrow?action={action}"
            )
            if i._autoReadAloud is not None:
                redirect_url += '&_autoReadAloud=' + i._autoReadAloud
            raise web.seeother(redirect_url)

        if action == 'return':
            lending.s3_loan_api(s3_keys, ocaid=edition.ocaid, action='return_loan')
            stats.increment('ol.loans.return')
            edition.update_loan_status()
            user.update_loan_status()
            raise web.seeother(edition_redirect)
        elif action == 'join-waitinglist':
            lending.get_cached_user_waiting_loans.memcache_delete(
                user.key, {}
            )  # invalidate cache for user waiting loans
            lending.s3_loan_api(s3_keys, ocaid=edition.ocaid, action='join_waitlist')
            stats.increment('ol.loans.joinWaitlist')
            raise web.redirect(edition_redirect)
        elif action == 'leave-waitinglist':
            lending.get_cached_user_waiting_loans.memcache_delete(
                user.key, {}
            )  # invalidate cache for user waiting loans
            lending.s3_loan_api(s3_keys, ocaid=edition.ocaid, action='leave_waitlist')
            stats.increment('ol.loans.leaveWaitlist')
            raise web.redirect(edition_redirect)

        elif action in ('borrow', 'browse') and not user.has_borrowed(edition):
            borrow_access = user_can_borrow_edition(user, edition)

            if not (s3_keys and borrow_access):
                stats.increment('ol.loans.outdatedAvailabilityStatus')
                raise web.seeother(error_redirect)

            try:
                lending.s3_loan_api(
                    s3_keys, ocaid=edition.ocaid, action='%s_book' % borrow_access
                )
                stats.increment('ol.loans.bookreader')
                stats.increment('ol.loans.%s' % borrow_access)
            except lending.PatronAccessException:
                stats.increment('ol.loans.blocked')

                add_flash_message(
                    'error',
                    _(
                        'Your account has hit a lending limit. Please try again later or contact info@archive.org.'
                    ),
                )
                raise web.seeother(key)

        if action in ('borrow', 'browse', 'read'):
            bookPath = '/stream/' + edition.ocaid
            if i._autoReadAloud is not None:
                bookPath += '?_autoReadAloud=show'

            # Look for loans for this book
            user.update_loan_status()
            loans = get_loans(user)
            for loan in loans:
                if loan['book'] == edition.key:
                    raise web.seeother(
                        make_bookreader_auth_link(
                            loan['_key'],
                            edition.ocaid,
                            bookPath,
                            ia_userid=ia_itemname,
                        )
                    )

        # Action not recognized
        raise web.seeother(error_redirect)


# Handler for /books/{bookid}/{title}/_borrow_status
class borrow_status(delegate.page):
    path = "(/books/.*)/_borrow_status"

    def GET(self, key):

        i = web.input(callback=None)

        edition = web.ctx.site.get(key)

        if not edition:
            raise web.notfound()

        edition.update_loan_status()
        available_formats = [
            loan['resource_type'] for loan in edition.get_available_loans()
        ]
        loan_available = len(available_formats) > 0
        subjects = set()

        for work in edition.get('works', []):
            for subject in work.get_subjects():
                if subject in lending_subjects:
                    subjects.add(subject)

        output = {
            'id': key,
            'loan_available': loan_available,
            'available_formats': available_formats,
            'lending_subjects': list(subjects),
        }

        output_text = json.dumps(output)

        content_type = "application/json"
        if i.callback:
            content_type = "text/javascript"
            output_text = f'{i.callback} ( {output_text} );'

        return delegate.RawText(output_text, content_type=content_type)


class ia_loan_status(delegate.page):
    path = r"/ia_loan_status/(.*)"

    def GET(self, itemid):
        d = get_borrow_status(itemid, include_resources=False, include_ia=False)
        return delegate.RawText(json.dumps(d), content_type="application/json")


@public
def get_borrow_status(itemid, include_resources=True, include_ia=True, edition=None):
    """Returns borrow status for each of the sources and formats.

    If the optional argument editions is provided, it uses that edition instead
    of finding edition from itemid. This is added for performance reasons.
    """
    loan = lending.get_loan(itemid)
    has_loan = bool(loan)

    if edition:
        editions = [edition]
    else:
        edition_keys = web.ctx.site.things({"type": "/type/edition", "ocaid": itemid})
        editions = web.ctx.site.get_many(edition_keys)
    has_waitinglist = editions and any(e.get_waitinglist_size() > 0 for e in editions)

    d = {
        'identifier': itemid,
        'checkedout': has_loan or has_waitinglist,
        'has_loan': has_loan,
        'has_waitinglist': has_waitinglist,
    }
    if include_ia:
        ia_checkedout = lending.is_loaned_out_on_ia(itemid)
        d['checkedout'] = d['checkedout'] or ia_checkedout
        d['checkedout_on_ia'] = ia_checkedout

    if include_resources:
        d.update(
            {
                'resource_bookreader': 'absent',
                'resource_pdf': 'absent',
                'resource_epub': 'absent',
            }
        )
        if editions:
            resources = editions[0].get_lending_resources()
            resource_pattern = r'acs:(\w+):(.*)'
            for resource_urn in resources:
                if resource_urn.startswith('acs:'):
                    (resource_type, resource_id) = re.match(
                        resource_pattern, resource_urn
                    ).groups()
                else:
                    resource_type, resource_id = "bookreader", resource_urn
                resource_type = "resource_" + resource_type
                if is_loaned_out(resource_id):
                    d[resource_type] = 'checkedout'
                else:
                    d[resource_type] = 'available'
    return web.storage(d)


# Handler for /borrow/receive_notification - receive ACS4 status update notifications
class borrow_receive_notification(delegate.page):
    path = r"/borrow/receive_notification"

    def GET(self):
        web.header('Content-Type', 'application/json')
        output = json.dumps({'success': False, 'error': 'Only POST is supported'})
        return delegate.RawText(output, content_type='application/json')

    def POST(self):
        data = web.data()
        try:
            etree.fromstring(data, parser=lxml.etree.XMLParser(resolve_entities=False))
            output = json.dumps({'success': True})
        except Exception as e:
            output = json.dumps({'success': False, 'error': str(e)})
        return delegate.RawText(output, content_type='application/json')


class ia_borrow_notify(delegate.page):
    """Invoked by archive.org to notify about change in loan/waiting list
    status of an item.

    The payload will be of the following format:

        {"identifier": "foo00bar"}
    """

    path = "/borrow/notify"

    def POST(self):
        payload = web.data()
        d = json.loads(payload)
        identifier = d and d.get('identifier')
        if identifier:
            lending.sync_loan(identifier)
            waitinglist.on_waitinglist_update(identifier)


# ######### Public Functions


@public
def is_loan_available(edition, type) -> bool:
    resource_id = edition.get_lending_resource_id(type)

    if not resource_id:
        return False

    return not is_loaned_out(resource_id)


@public
def datetime_from_isoformat(expiry):
    """Returns datetime object, or None"""
    return None if expiry is None else parse_datetime(expiry)


@public
def datetime_from_utc_timestamp(seconds):
    return datetime.utcfromtimestamp(seconds)


@public
def can_return_resource_type(resource_type: str) -> bool:
    """Returns true if this resource can be returned from the OL site."""
    return resource_type.startswith('bookreader')


@public
def get_bookreader_stream_url(itemid: str) -> str:
    return bookreader_stream_base + '/' + itemid


@public
def get_bookreader_host() -> str:
    return bookreader_host


# ######### Helper Functions


def get_all_store_values(**query) -> list:
    """Get all values by paging through all results. Note: adds store_key with the row id."""
    query = copy.deepcopy(query)
    if 'limit' not in query:
        query['limit'] = 500
    query['offset'] = 0
    values = []
    got_all = False

    while not got_all:
        # new_values = web.ctx.site.store.values(**query)
        new_items = web.ctx.site.store.items(**query)
        for new_item in new_items:
            new_item[1].update({'store_key': new_item[0]})
            # XXX-Anand: Handling the existing loans
            new_item[1].setdefault("ocaid", None)
            values.append(new_item[1])
        if len(new_items) < query['limit']:
            got_all = True
        query['offset'] += len(new_items)
    return values


def get_all_loans() -> list:
    # return web.ctx.site.store.values(type='/type/loan')
    return get_all_store_values(type='/type/loan')


def get_loans(user):
    return lending.get_loans_of_user(user.key)


def get_edition_loans(edition):
    if edition.ocaid:
        loan = lending.get_loan(edition.ocaid)
        if loan:
            return [loan]
    return []


def get_loan_link(edition, type):
    """Get the loan link, which may be an ACS4 link or BookReader link depending on the loan type"""
    resource_id = edition.get_lending_resource_id(type)

    if type == 'bookreader':
        # link to bookreader
        return (resource_id, get_bookreader_stream_url(edition.ocaid))

    raise Exception(
        'Unknown resource type %s for loan of edition %s', edition.key, type
    )


def get_loan_key(resource_id: str):
    """Get the key for the loan associated with the resource_id"""
    # Find loan in OL
    loan_keys = web.ctx.site.store.query('/type/loan', 'resource_id', resource_id)
    if not loan_keys:
        # No local records
        return None

    # Only support single loan of resource at the moment
    if len(loan_keys) > 1:
        # raise Exception('Found too many local loan records for resource %s' % resource_id)
        logger.error(
            "Found too many loan records for resource %s: %s", resource_id, loan_keys
        )

    loan_key = loan_keys[0]['key']
    return loan_key


def is_loaned_out(resource_id: str) -> bool | None:
    # bookreader loan status is stored in the private data store

    # Check our local status
    loan_key = get_loan_key(resource_id)
    if not loan_key:
        # No loan recorded
        identifier = resource_id[len('bookreader:') :]
        return lending.is_loaned_out_on_ia(identifier)

    # Find the loan and check if it has expired
    loan = web.ctx.site.store.get(loan_key)
    return bool(loan and datetime_from_isoformat(loan['expiry']) < datetime.utcnow())


def is_loaned_out_from_status(status) -> bool:
    return status and status['returned'] != 'T'


def user_can_borrow_edition(user, edition) -> Literal['borrow', 'browse', False]:
    """Returns the type of borrow for which patron is eligible, favoring
    "browse" over "borrow" where available, otherwise return False if
    patron is not eligible.

    """
    lending_st = lending.get_groundtruth_availability(edition.ocaid, {})

    book_is_lendable = lending_st.get('is_lendable', False)
    book_is_waitlistable = lending_st.get('available_to_waitlist', False)
    user_is_below_loan_limit = user.get_loan_count() < user_max_loans

    if book_is_lendable:
        if web.cookies().get('pd', False):
            return 'borrow'
        elif user_is_below_loan_limit:
            if lending_st.get('available_to_browse'):
                return 'browse'
            elif lending_st.get('available_to_borrow') or (
                book_is_waitlistable and is_users_turn_to_borrow(user, edition)
            ):
                return 'borrow'
    return False


def is_users_turn_to_borrow(user, edition) -> bool:
    """If this user is waiting on this edition, it can only borrowed if
    user is the user is the first in the waiting list.
    """
    waiting_loan = user.get_waiting_loan_for(edition.ocaid)
    return (
        waiting_loan
        and waiting_loan['status'] == 'available'
        and waiting_loan['position'] == 1
    )


def is_admin() -> bool:
    """Returns True if the current user is in admin usergroup."""
    user = accounts.get_current_user()
    return user is not None and user.key in [
        m.key for m in web.ctx.site.get('/usergroup/admin').members
    ]


def return_resource(resource_id):
    """Return the book to circulation!  This object is invalid and should not be used after
    this is called.  Currently only possible for bookreader loans."""
    loan_key = get_loan_key(resource_id)
    if not loan_key:
        raise Exception('Asked to return %s but no loan recorded' % resource_id)

    loan = web.ctx.site.store.get(loan_key)

    delete_loan(loan_key, loan)


def delete_loan(loan_key, loan=None) -> None:
    if not loan:
        loan = web.ctx.site.store.get(loan_key)
        if not loan:
            raise Exception('Could not find store record for %s', loan_key)

    loan.delete()


def ia_hash(token_data: str) -> str:
    try:
        access_key = config.ia_access_secret.encode('utf-8')  # type: ignore[attr-defined]
    except AttributeError:
        raise RuntimeError(
            "config value config.ia_access_secret is not present -- check your config"
        )
    return hmac.new(access_key, token_data.encode('utf-8'), hashlib.md5).hexdigest()


def make_ia_token(item_id: str, expiry_seconds: int) -> str:
    """Make a key that allows a client to access the item on archive.org for the number of
    seconds from now.
    """
    # $timestamp = $time+600; //access granted for ten minutes
    # $hmac = hash_hmac('md5', "{$id}-{$timestamp}", configGetValue('ol-loan-secret'));
    # return "{$timestamp}-{$hmac}";

    timestamp = int(time.time() + expiry_seconds)
    token_data = '%s-%d' % (item_id, timestamp)
    token = '%d-%s' % (timestamp, ia_hash(token_data))
    return token


def make_bookreader_auth_link(loan_key, item_id, book_path, ia_userid=None) -> str:
    """
    Generate a link to BookReaderAuth.php that starts the BookReader
    with the information to initiate reading a borrowed book
    """
    auth_link = 'https://%s/bookreader/BookReaderAuth.php?' % bookreader_host
    params = {
        'uuid': loan_key,
        'token': make_ia_token(item_id, BOOKREADER_AUTH_SECONDS),
        'id': item_id,
        'bookPath': book_path,
        'iaUserId': ia_userid,
        'iaAuthToken': make_ia_token(ia_userid, READER_AUTH_SECONDS),
    }
    return auth_link + urllib.parse.urlencode(params)


lending.setup(config)
vendors.setup(config)
