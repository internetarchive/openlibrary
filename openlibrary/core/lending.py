"""Module for providing core functionality of lending on Open Library.
"""
from typing import Literal, Optional

import web
import datetime
import logging
import random
import time
import uuid

import eventer
import requests

from infogami.utils.view import public
from infogami.utils import delegate
from openlibrary.core import cache
from openlibrary.accounts.model import OpenLibraryAccount
from openlibrary.plugins.upstream.utils import urlencode
from openlibrary.utils import dateutil, uniq

from . import ia
from . import helpers as h

logger = logging.getLogger(__name__)

S3_LOAN_URL = 'https://%s/services/loans/loan/'

# When we generate a loan offer (.acsm) for a user we assume that the loan has occurred.
# Once the loan fulfillment inside Digital Editions the book status server will know
# the loan has occurred.  We allow this timeout so that we don't delete the OL loan
# record before fulfillment because we can't find it in the book status server.
# $$$ If a user borrows an ACS4 book and immediately returns book loan will show as
#     "not yet downloaded" for the duration of the timeout.
#     BookReader loan status is always current.
LOAN_FULFILLMENT_TIMEOUT_SECONDS = dateutil.MINUTE_SECS * 5

# How long bookreader loans should last
BOOKREADER_LOAN_DAYS = 14

BOOKREADER_STREAM_URL_PATTERN = "https://{0}/stream/{1}"
DEFAULT_IA_RESULTS = 42
MAX_IA_RESULTS = 1000


config_ia_loan_api_url = None
config_ia_xauth_api_url = None
config_ia_availability_api_v2_url = None
config_ia_access_secret = None
config_ia_domain = None
config_ia_ol_shared_key = None
config_ia_ol_xauth_s3 = None
config_ia_s3_auth_url = None
config_ia_ol_metadata_write_s3 = None
config_ia_users_loan_history = None
config_ia_loan_api_developer_key = None
config_ia_civicrm_api = None
config_http_request_timeout = None
config_loanstatus_url = None
config_bookreader_host = None
config_internal_tests_api_key = None


def setup(config):
    """Initializes this module from openlibrary config."""
    global config_loanstatus_url, config_ia_access_secret, config_bookreader_host, config_ia_ol_shared_key, config_ia_ol_xauth_s3, config_internal_tests_api_key, config_ia_loan_api_url, config_http_request_timeout, config_ia_availability_api_v2_url, config_ia_ol_metadata_write_s3, config_ia_xauth_api_url, config_http_request_timeout, config_ia_s3_auth_url, config_ia_users_loan_history, config_ia_loan_api_developer_key, config_ia_civicrm_api, config_ia_domain

    config_loanstatus_url = config.get('loanstatus_url')
    config_bookreader_host = config.get('bookreader_host', 'archive.org')
    config_ia_domain = config.get('ia_base_url', 'https://archive.org')
    config_ia_loan_api_url = config.get('ia_loan_api_url')
    config_ia_availability_api_v2_url = config.get('ia_availability_api_v2_url')
    config_ia_xauth_api_url = config.get('ia_xauth_api_url')
    config_ia_access_secret = config.get('ia_access_secret')
    config_ia_ol_shared_key = config.get('ia_ol_shared_key')
    config_ia_ol_auth_key = config.get('ia_ol_auth_key')
    config_ia_ol_xauth_s3 = config.get('ia_ol_xauth_s3')
    config_ia_ol_metadata_write_s3 = config.get('ia_ol_metadata_write_s3')
    config_ia_s3_auth_url = config.get('ia_s3_auth_url')
    config_ia_users_loan_history = config.get('ia_users_loan_history')
    config_ia_loan_api_developer_key = config.get('ia_loan_api_developer_key')
    config_ia_civicrm_api = config.get('ia_civicrm_api')
    config_internal_tests_api_key = config.get('internal_tests_api_key')
    config_http_request_timeout = config.get('http_request_timeout')


def get_work_authors_and_related_subjects(work_id):
    if 'env' not in web.ctx:
        delegate.fakeload()
    work = web.ctx.site.get(work_id)
    return {
        'authors': work.get_author_names(blacklist=['anonymous']) if work else [],
        'subjects': work.get_related_books_subjects() if work else [],
    }


@public
def cached_work_authors_and_subjects(work_id):
    try:
        return cache.memcache_memoize(
            get_work_authors_and_related_subjects,
            'works_authors_and_subjects',
            timeout=dateutil.HALF_DAY_SECS,
        )(work_id)
    except AttributeError:
        logger.exception("cached_work_authors_and_subjects(%s)" % work_id)
        return {'authors': [], 'subject': []}


@public
def compose_ia_url(
    limit: int = None,
    page: int = 1,
    subject=None,
    query=None,
    work_id=None,
    _type: Literal['authors', 'subjects'] = None,
    sorts=None,
    advanced=True,
    rate_limit_exempt=True,
) -> Optional[str]:
    """This needs to be exposed by a generalized API endpoint within
    plugins/api/browse which lets lazy-load more items for
    the homepage carousel and support the upcoming /browse view
    (backed by archive.org search, so we don't have to send users to
    archive.org to see more books)

    Returns None if we get an empty query
    """
    from openlibrary.plugins.openlibrary.home import CAROUSELS_PRESETS

    query = CAROUSELS_PRESETS.get(query, query)
    q = 'openlibrary_work:(*)'

    # If we don't provide an openlibrary_subject and no collection is
    # specified in our query, we restrict our query to the `inlibrary`
    # collection (i.e. those books which are borrowable)
    if (not subject) and (not query or 'collection:' not in query):
        q += ' AND collection:(inlibrary)'
    # In the only case where we are not restricting our search to
    # borrowable books (i.e. `inlibrary`), we remove all the books
    # which are `printdisabled` *outside* of `inlibrary`.
    if 'collection:(inlibrary)' not in q:
        q += ' AND (collection:(inlibrary) OR (!collection:(printdisabled)))'

    # If no lending restrictions (e.g. borrow, read) are imposed in
    # our query, we assume only borrowable books will be included in
    # results (not unrestricted/open books).
    lendable = (
        '(lending___available_to_browse:true OR lending___available_to_borrow:true)'
    )
    if (not query) or lendable not in query:
        q += ' AND ' + lendable
    if query:
        q += " AND " + query
    if subject:
        q += " AND openlibrary_subject:" + subject

    if work_id and _type in ("authors", "subjects"):
        _q = None
        works_authors_and_subjects = cached_work_authors_and_subjects(work_id)
        if _type == "authors":
            authors = works_authors_and_subjects.get('authors', [])
            if not authors:
                return None
            name_variations = [
                variation
                for name in authors
                for variation in (name, ','.join(name.split(' ', 1)[::-1]))
            ]

            _q = ' OR '.join(f'creator:"{name}"' for name in name_variations)
        elif _type == "subjects":
            subjects = works_authors_and_subjects.get('subjects', [])
            if not subjects:
                return None
            _q = ' OR '.join(f'subject:"{subject}"' for subject in subjects)
        q += ' AND ({}) AND !openlibrary_work:({})'.format(_q, work_id.split('/')[-1])

    if not advanced:
        _sort = sorts[0] if sorts else ''
        if ' desc' in _sort:
            _sort = '-' + _sort.split(' desc')[0]
        elif ' asc' in _sort:
            _sort = _sort.split(' asc')[0]
        simple_params = {'query': q}
        if _sort:
            simple_params['sort'] = _sort
        return 'https://archive.org/search.php?' + urlencode(simple_params)

    rows = limit or DEFAULT_IA_RESULTS
    params = [
        ('q', q),
        ('fl[]', 'identifier'),
        ('fl[]', 'openlibrary_edition'),
        ('fl[]', 'openlibrary_work'),
        ('rows', rows),
        ('page', page),
        ('output', 'json'),
    ]
    if rate_limit_exempt:
        params.append(('service', 'metadata__unlimited'))
    if not sorts or not isinstance(sorts, list):
        sorts = ['']
    for sort in sorts:
        params.append(('sort[]', sort))
    base_url = "http://%s/advancedsearch.php" % config_bookreader_host
    return base_url + '?' + urlencode(params)


def get_random_available_ia_edition() -> str:
    """uses archive advancedsearch to raise a random book"""
    try:
        url = (
            "http://%s/advancedsearch.php?q=_exists_:openlibrary_work"
            "+AND+(lending___available_to_borrow:true"
            " OR lending___available_to_browse:true)"
            "&fl=identifier,openlibrary_edition"
            "&output=json&rows=25&sort[]=random" % (config_bookreader_host)
        )  # internetarchive/openlibrary#6592: Request 25 editions and randomly choose
        response = requests.get(url, timeout=config_http_request_timeout)
        items = response.json().get('response', {}).get('docs', [])
        return random.choice(items)["openlibrary_edition"]
    except Exception:  # TODO: Narrow exception scope
        logger.exception(f"get_random_available_ia_edition({url})")
        return ''


@public
@cache.memoize(
    engine="memcache", key="gt-availability", expires=5 * dateutil.MINUTE_SECS
)
def get_cached_groundtruth_availability(ocaid):
    return get_groundtruth_availability(ocaid)


def get_groundtruth_availability(ocaid, s3_keys=None):
    """temporary stopgap to get ground-truth availability of books
    including 1-hour borrows"""
    params = '?action=availability&identifier=' + ocaid
    url = S3_LOAN_URL % config_bookreader_host
    try:
        response = requests.post(url + params, data=s3_keys)
        response.raise_for_status()
    except requests.HTTPError:
        pass  # TODO: Handle unexpected responses from the availability server.
    data = response.json().get('lending_status', {})
    # For debugging
    data['__src__'] = 'core.models.lending.get_groundtruth_availability'
    return data


def s3_loan_api(ocaid, s3_keys, action='browse'):
    """Uses patrons s3 credentials to initiate or return a browse or
    borrow loan on Archive.org.

    :param dict s3_keys: {'access': 'xxx', 'secret': 'xxx'}
    :param str action: 'browse_book' or 'borrow_book' or 'return_loan'

    """
    params = f'?action={action}&identifier={ocaid}'
    url = S3_LOAN_URL % config_bookreader_host
    return requests.post(url + params, data=s3_keys)


def get_available(
    limit=None,
    page=1,
    subject=None,
    query=None,
    work_id=None,
    _type=None,
    sorts=None,
    url=None,
):
    """Experimental. Retrieves a list of available editions from
    archive.org advancedsearch which are available, in the inlibrary
    collection, and optionally apart of an `openlibrary_subject`.

    Returns a list of editions (one available edition per work). Is
    used in such things as 'Staff Picks' carousel to retrieve a list
    of unique available books.
    """

    url = url or compose_ia_url(
        limit=limit,
        page=page,
        subject=subject,
        query=query,
        work_id=work_id,
        _type=_type,
        sorts=sorts,
    )
    if not url:
        logger.error(
            'get_available failed',
            extra={
                'limit': limit,
                'page': page,
                'subject': subject,
                'query': query,
                'work_id': work_id,
                'type': _type,
                'sorts': sorts,
            },
        )
        return {'error': 'no_url'}
    try:
        # Internet Archive Elastic Search (which powers some of our
        # carousel queries) needs Open Library to forward user IPs so
        # we can attribute requests to end-users
        client_ip = web.ctx.env.get('HTTP_X_FORWARDED_FOR', 'ol-internal')
        headers = {
            "x-client-id": client_ip,
            "x-preferred-client-id": client_ip,
            "x-application-id": "openlibrary"
        }
        response = requests.get(
            url, headers=headers, timeout=config_http_request_timeout
        )
        items = response.json().get('response', {}).get('docs', [])
        results = {}
        for item in items:
            if item.get('openlibrary_work'):
                results[item['openlibrary_work']] = item['openlibrary_edition']
        books = web.ctx.site.get_many(['/books/%s' % olid for olid in results.values()])
        books = add_availability(books)
        return books
    except Exception:  # TODO: Narrow exception scope
        logger.exception("get_available(%s)" % url)
        return {'error': 'request_timeout'}


def get_availability(key, ids):
    """
    :param str key: the type of identifier
    :param list of str ids:
    :rtype: dict
    """
    ids = [id_ for id_ in ids if id_]  # remove infogami.infobase.client.Nothing
    if not ids:
        return {}

    def update_availability_schema_to_v2(v1_resp, ocaid):
        """This functionattempts to take the output of e.g. Bulk Availability
        API and add/infer attributes which are missing (but are
        present on Ground Truth API)
        """
        # TODO: Make less brittle; maybe add simplelists/copy counts to Bulk Availability
        v1_resp['identifier'] = ocaid
        v1_resp['is_restricted'] = v1_resp['status'] != 'open'
        v1_resp['is_browseable'] = v1_resp.get('available_to_browse', False)
        # For debugging
        v1_resp['__src__'] = 'core.models.lending.get_availability'
        return v1_resp

    url = '{}?{}={}'.format(config_ia_availability_api_v2_url, key, ','.join(ids))
    try:
        response = requests.get(url, timeout=config_http_request_timeout)
        items = response.json().get('responses', {})
        for pkey in items:
            ocaid = pkey if key == 'identifier' else items[pkey].get('identifier')
            items[pkey] = update_availability_schema_to_v2(items[pkey], ocaid)
        return items
    except Exception as e:  # TODO: Narrow exception scope
        logger.exception("get_availability(%s)" % url)
        items = {'error': 'request_timeout', 'details': str(e)}

        for pkey in ids:
            # key could be isbn, ocaid, or openlibrary_[work|edition]
            ocaid = pkey if key == 'identifier' else None
            items[pkey] = update_availability_schema_to_v2({'status': 'error'}, ocaid)
        return items


def get_edition_availability(ol_edition_id):
    return get_availability_of_editions([ol_edition_id])


def get_availability_of_editions(ol_edition_ids):
    """Given a list of Open Library edition IDs, returns a list of
    Availability v2 results.
    """
    return get_availability('openlibrary_edition', ol_edition_ids)


def get_ocaid(item):
    # Circular import otherwise
    from ..book_providers import is_non_ia_ocaid

    possible_fields = [
        'ocaid',  # In editions
        'identifier',  # In ?? not editions/works/solr
        'ia',  # In solr work records and worksearch get_docs
        'lending_identifier',  # In solr works records + worksearch get_doc
    ]
    # SOLR WORK RECORDS ONLY:
    # Open Library only has access to a list of archive.org IDs
    # and solr isn't currently equipped with the information
    # necessary to determine which editions may be openly
    # available. Using public domain date as a heuristic
    # Long term solution is a full reindex, but this hack will work in the
    # vast majority of cases for now.
    # NOTE: there is still a risk pre-1923 books will get a print-diabled-only
    # or lendable edition.
    # Note: guaranteed to be int-able if none None
    US_PD_YEAR = 1923
    if float(item.get('first_publish_year') or '-inf') > US_PD_YEAR:
        # Prefer `lending_identifier` over `ia` (push `ia` to bottom)
        possible_fields.remove('ia')
        possible_fields.append('ia')

    ocaids = []
    for field in possible_fields:
        if item.get(field):
            ocaids += item[field] if isinstance(item[field], list) else [item[field]]
    ocaids = uniq(ocaids)
    return next((ocaid for ocaid in ocaids if not is_non_ia_ocaid(ocaid)), None)


@public
def get_availabilities(items: list) -> dict:
    result = {}
    ocaids = [ocaid for ocaid in map(get_ocaid, items) if ocaid]
    availabilities = get_availability_of_ocaids(ocaids)
    for item in items:
        ocaid = get_ocaid(item)
        if ocaid:
            result[item['key']] = availabilities.get(ocaid)
    return result


@public
def add_availability(
    items: list,
    mode: Literal['identifier', 'openlibrary_work'] = "identifier",
) -> list:
    """
    Adds API v2 'availability' key to dicts
    :param items: items with fields containing ocaids
    """
    if mode == "identifier":
        ocaids = [ocaid for ocaid in map(get_ocaid, items) if ocaid]
        availabilities = get_availability_of_ocaids(ocaids)
        for item in items:
            ocaid = get_ocaid(item)
            if ocaid:
                item['availability'] = availabilities.get(ocaid)
    elif mode == "openlibrary_work":
        _ids = [item['key'].split('/')[-1] for item in items]
        availabilities = get_availability_of_works(_ids)
        for item in items:
            olid = item['key'].split('/')[-1]
            if olid:
                item['availability'] = availabilities.get(olid)
    return items


@public
def get_availability_of_ocaid(ocaid):
    """Retrieves availability based on ocaid/archive.org identifier"""
    return get_availability('identifier', [ocaid])


def get_availability_of_ocaids(ocaids):
    """
    Retrieves availability based on ocaids/archive.org identifiers
    :param list[str] ocaids:
    :rtype: dict
    """
    return get_availability('identifier', ocaids)


@public
def get_work_availability(ol_work_id):
    return get_availability_of_works([ol_work_id])


def get_availability_of_works(ol_work_ids):
    return get_availability('openlibrary_work', ol_work_ids)


def is_loaned_out(identifier):
    """Returns True if the given identifier is loaned out.

    This doesn't worry about waiting lists.
    """
    # is_loaned_out_on_acs4 is to be deprecated, this logic (in PR)
    # should be handled by is_loaned_out_on_ia which calls
    # BorrowBooks.inc in petabox
    return (
        is_loaned_out_on_ol(identifier)
        or is_loaned_out_on_acs4(identifier)
        or is_loaned_out_on_ia(identifier)
    )


def is_loaned_out_on_acs4(identifier):
    """Returns True if the item is checked out on acs4 server."""
    item = ACS4Item(identifier)
    return item.has_loan()


def is_loaned_out_on_ia(identifier):
    """Returns True if the item is checked out on Internet Archive."""
    url = "https://archive.org/services/borrow/%s?action=status" % identifier
    try:
        response = requests.get(url).json()
        return response and response.get('checkedout')
    except Exception:  # TODO: Narrow exception scope
        logger.exception("is_loaned_out_on_ia(%s)" % identifier)
        return None


def is_loaned_out_on_ol(identifier):
    """Returns True if the item is checked out on Open Library."""
    loan = get_loan(identifier)
    return bool(loan)


def get_loan(identifier, user_key=None):
    """Returns the loan object for given identifier, if a loan exists.

    If user_key is specified, it returns the loan only if that user is
    borrowed that book.
    """
    _loan = None
    account = None
    if user_key:
        if user_key.startswith('@'):
            account = OpenLibraryAccount.get(link=user_key)
        else:
            account = OpenLibraryAccount.get(key=user_key)

    d = web.ctx.site.store.get("loan-" + identifier)
    if d and (
        user_key is None
        or (d['user'] == account.username)
        or (d['user'] == account.itemname)
    ):
        loan = Loan(d)
        if loan.is_expired():
            return loan.delete()
    try:
        _loan = _get_ia_loan(identifier, account and userkey2userid(account.username))
    except Exception:  # TODO: Narrow exception scope
        logger.exception("get_loan(%s) 1 of 2" % identifier)

    try:
        _loan = _get_ia_loan(identifier, account and account.itemname)
    except Exception:  # TODO: Narrow exception scope
        logger.exception("get_loan(%s) 2 of 2" % identifier)

    return _loan


def _get_ia_loan(identifier, userid):
    ia_loan = ia_lending_api.get_loan(identifier, userid)
    return ia_loan and Loan.from_ia_loan(ia_loan)


def get_loans_of_user(user_key):
    """TODO: Remove inclusion of local data; should only come from IA"""
    account = OpenLibraryAccount.get(username=user_key.split('/')[-1])

    loandata = web.ctx.site.store.values(type='/type/loan', name='user', value=user_key)
    loans = [Loan(d) for d in loandata] + (
        _get_ia_loans_of_user(account.itemname)
    )
    return loans


def _get_ia_loans_of_user(userid):
    ia_loans = ia_lending_api.find_loans(userid=userid)
    return [Loan.from_ia_loan(d) for d in ia_loans]


def create_loan(identifier, resource_type, user_key, book_key=None):
    """Creates a loan and returns it."""
    ia_loan = ia_lending_api.create_loan(
        identifier=identifier, format=resource_type, userid=user_key, ol_key=book_key
    )

    if ia_loan:
        loan = Loan.from_ia_loan(ia_loan)
        eventer.trigger("loan-created", loan)
        sync_loan(identifier)
        return loan

    # loan = Loan.new(identifier, resource_type, user_key, book_key)
    # loan.save()
    # return loan


NOT_INITIALIZED = object()


def sync_loan(identifier, loan=NOT_INITIALIZED):
    """Updates the loan info stored in openlibrary.

    The loan records are stored at the Internet Archive. There is no way for
    OL to know when a loan is deleted. To handle that situation, the loan info
    is stored in the ebook document and the deletion is detected by comparing
    the current loan id and loan id stored in the ebook.

    This function is called whenever the loan is updated.
    """
    logger.info("BEGIN sync_loan %s %s", identifier, loan)

    if loan is NOT_INITIALIZED:
        loan = get_loan(identifier)

    # The data of the loan without the user info.
    loan_data = loan and dict(
        uuid=loan['uuid'],
        loaned_at=loan['loaned_at'],
        resource_type=loan['resource_type'],
        ocaid=loan['ocaid'],
        book=loan['book'],
    )

    responses = get_availability_of_ocaid(identifier)
    response = responses[identifier] if responses else {}
    if response:
        num_waiting = int(response.get('num_waitlist', 0) or 0)

    ebook = EBookRecord.find(identifier)

    # The loan known to us is deleted
    is_loan_completed = ebook.get("loan") and ebook.get("loan") != loan_data

    # When the current loan is a OL loan, remember the loan_data
    if loan and loan.is_ol_loan():
        ebook_loan_data = loan_data
    else:
        ebook_loan_data = None

    kwargs = {
        "type": "ebook",
        "identifier": identifier,
        "loan": ebook_loan_data,
        "borrowed": str(response['status'] not in ['open', 'borrow_available']).lower(),
        "wl_size": num_waiting,
    }
    try:
        ebook.update(**kwargs)
    except Exception:  # TODO: Narrow exception scope
        # updating ebook document is sometimes failing with
        # "Document update conflict" error.
        # Log the error in such cases, don't crash.
        logger.exception("failed to update ebook for %s", identifier)

    # fire loan-completed event
    if is_loan_completed and ebook.get('loan'):
        _d = dict(ebook['loan'], returned_at=time.time())
        eventer.trigger("loan-completed", _d)
    logger.info("END sync_loan %s", identifier)


class EBookRecord(dict):
    @staticmethod
    def find(identifier):
        key = "ebooks/" + identifier
        d = web.ctx.site.store.get(key) or {"_key": key, "type": "ebook", "_rev": 1}
        return EBookRecord(d)

    def update(self, **kwargs):
        logger.info("updating %s %s", self['_key'], kwargs)
        # Nothing to update if what we have is same as what is being asked to
        # update.
        d = {k: self.get(k) for k in kwargs}
        if d == kwargs:
            return

        dict.update(self, **kwargs)
        web.ctx.site.store[self['_key']] = self


class Loan(dict):
    """Model for loan."""

    @staticmethod
    def new(identifier, resource_type, user_key, book_key=None):
        """Creates a new loan object.

        The caller is expected to call save method to save the loan.
        """
        if book_key is None:
            book_key = "/books/ia:" + identifier
        _uuid = uuid.uuid4().hex
        loaned_at = time.time()

        if resource_type == "bookreader":
            resource_id = "bookreader:" + identifier
            loan_link = BOOKREADER_STREAM_URL_PATTERN.format(
                config_bookreader_host, identifier
            )
            expiry = (
                datetime.datetime.utcnow()
                + datetime.timedelta(days=BOOKREADER_LOAN_DAYS)
            ).isoformat()
        else:
            raise Exception(
                'No longer supporting ACS borrows directly from Open Library. Please go to Archive.org'
            )

        if not resource_id:
            raise Exception(
                f'Could not find resource_id for {identifier} - {resource_type}'
            )

        key = "loan-" + identifier
        return Loan(
            {
                '_key': key,
                '_rev': 1,
                'type': '/type/loan',
                'fulfilled': 1,
                'user': user_key,
                'book': book_key,
                'ocaid': identifier,
                'expiry': expiry,
                'uuid': _uuid,
                'resource_type': 'bookreader',
                'resource_id': 'bookreader:%s' % identifier,
                'loaned_at': loaned_at,
                'resource_type': resource_type,
                'resource_id': resource_id,
                'loan_link': loan_link,
            }
        )

    @staticmethod
    def from_ia_loan(data):
        if data['userid'].startswith('ol:'):
            user_key = '/people/' + data['userid'][len('ol:') :]
        elif data['userid'].startswith('@'):
            account = OpenLibraryAccount.get_by_link(data['userid'])
            user_key = ('/people/' + account.username) if account else None
        else:
            user_key = None

        if data['ol_key']:
            book_key = data['ol_key']
        else:
            book_key = resolve_identifier(data['identifier'])

        created = h.parse_datetime(data['created'])

        # For historic reasons, OL considers expiry == None as un-fulfilled
        # loan.

        expiry = data.get('until')

        d = {
            '_key': "loan-{}".format(data['identifier']),
            '_rev': 1,
            'type': '/type/loan',
            'userid': data['userid'],
            'user': user_key,
            'book': book_key,
            'ocaid': data['identifier'],
            'expiry': expiry,
            'fulfilled': data['fulfilled'],
            'uuid': 'loan-{}'.format(data['id']),
            'loaned_at': time.mktime(created.timetuple()),
            'resource_type': data['format'],
            'resource_id': data['resource_id'],
            'loan_link': data['loan_link'],
            'stored_at': 'ia',
        }
        return Loan(d)

    def is_ol_loan(self):
        # self['user'] will be None for IA loans
        return self['user'] is not None

    def get_key(self):
        return self['_key']

    def save(self):
        # loans stored at IA are not supposed to be saved at OL.
        # This call must have been made in mistake.
        if self.get("stored_at") == "ia":
            return

        web.ctx.site.store[self['_key']] = self

        # Inform listers that a loan is created/updated
        eventer.trigger("loan-created", self)

    def is_expired(self):
        return (
            self['expiry'] and self['expiry'] < datetime.datetime.utcnow().isoformat()
        )

    def is_yet_to_be_fulfilled(self):
        """Returns True if the loan is not yet fulfilled and fulfillment time
        is not expired.
        """
        return (
            self['expiry'] is None
            and (time.time() - self['loaned_at']) < LOAN_FULFILLMENT_TIMEOUT_SECONDS
        )

    def return_loan(self):
        logger.info("*** return_loan ***")
        if self['resource_type'] == 'bookreader':
            self.delete()
            return True
        else:
            return False

    def delete(self):
        loan = dict(self, returned_at=time.time())
        user_key = self['user']
        account = OpenLibraryAccount.get(key=user_key)
        if self.get("stored_at") == 'ia':
            ia_lending_api.delete_loan(self['ocaid'], userkey2userid(user_key))
            if account.itemname:
                ia_lending_api.delete_loan(self['ocaid'], account.itemname)
        else:
            web.ctx.site.store.delete(self['_key'])

        sync_loan(self['ocaid'])
        # Inform listers that a loan is completed
        eventer.trigger("loan-completed", loan)


def resolve_identifier(identifier):
    """Returns the OL book key for given IA identifier."""
    keys = web.ctx.site.things(dict(type='/type/edition', ocaid=identifier))
    if keys:
        return keys[0]
    else:
        return "/books/ia:" + identifier


def userkey2userid(user_key):
    username = user_key.split("/")[-1]
    return "ol:" + username


def get_resource_id(identifier, resource_type):
    """Returns the resource_id for an identifier for the specified resource_type.

    The resource_id is found by looking at external_identifiers field in the
    metadata of the item.
    """
    if resource_type == "bookreader":
        return "bookreader:" + identifier

    metadata = ia.get_metadata(identifier)
    external_identifiers = metadata.get("external-identifier", [])

    for eid in external_identifiers:
        # Ignore bad external identifiers
        if eid.count(":") < 2:
            continue

        # The external identifiers will be of the format
        # acs:epub:<resource_id> or acs:pdf:<resource_id>
        acs, rtype, resource_id = eid.split(":", 2)
        if rtype == resource_type:
            return resource_id


def update_loan_status(identifier):
    """Update the loan status in OL based off status in ACS4.  Used to check for early returns."""
    loan = get_loan(identifier)

    # if the loan is from ia, it is already updated when getting the loan
    if loan is None or loan.get('from_ia'):
        return

    if loan['resource_type'] == 'bookreader':
        if loan.is_expired():
            loan.delete()
            return
    else:
        acs4_loan = ACS4Item(identifier).get_loan()
        if not acs4_loan and not loan.is_yet_to_be_fulfilled():
            logger.info(
                "%s: loan returned or expired or timedout, deleting...", identifier
            )
            loan.delete()
            return

        if loan['expiry'] != acs4_loan['until']:
            loan['expiry'] = acs4_loan['until']
            loan.save()
            logger.info("%s: updated expiry to %s", identifier, loan['expiry'])


class ACS4Item:
    """Represents an item on ACS4 server.

    An item can have multiple resources (epub/pdf) and any of them could be loanded out.

    This class provides a way to access the loan info from ACS4 server.
    """

    def __init__(self, identifier):
        self.identifier = identifier

    def get_data(self):
        url = f'{config_loanstatus_url}/item/{self.identifier}'
        try:
            return requests.get(url).json()
        except OSError:
            logger.exception("unable to conact BSS server")

    def has_loan(self):
        return bool(self.get_loan())

    def get_loan(self):
        """Returns the information about loan in the ACS4 server."""
        d = self.get_data() or {}
        if not d.get('resources'):
            return
        for r in d['resources']:
            if r['loans']:
                loan = dict(r['loans'][0])
                loan['resource_id'] = r['resourceid']
                loan['resource_type'] = self._format2resource_type(r['format'])
                return loan

    def _format2resource_type(self, format):
        formats = {"application/epub+zip": "epub", "application/pdf": "pdf"}
        return formats[format]


class IA_Lending_API:
    """Archive.org waiting list API."""

    def get_loan(self, identifier, userid=None):
        params = dict(method="loan.query", identifier=identifier)
        if userid:
            params['userid'] = userid
        loans = self._post(**params).get('result', [])
        if loans:
            return loans[0]

    def find_loans(self, **kw):
        return self._post(method="loan.query", **kw).get('result', [])

    def create_loan(self, identifier, userid, format, ol_key):
        response = self._post(
            method="loan.create",
            identifier=identifier,
            userid=userid,
            format=format,
            ol_key=ol_key,
        )
        if response['status'] == 'ok':
            return response['result']['loan']

    def delete_loan(self, identifier, userid):
        self._post(method="loan.delete", identifier=identifier, userid=userid)

    def get_waitinglist_of_book(self, identifier):
        return self.query(identifier=identifier)

    def get_waitinglist_of_user(self, userid):
        return self.query(userid=userid)

    def join_waitinglist(self, identifier, userid):
        return self._post(
            method="waitinglist.join", identifier=identifier, userid=userid
        )

    def leave_waitinglist(self, identifier, userid):
        return self._post(
            method="waitinglist.leave", identifier=identifier, userid=userid
        )

    def update_waitinglist(self, identifier, userid, **kwargs):
        return self._post(
            method="waitinglist.update", identifier=identifier, userid=userid, **kwargs
        )

    def query(self, **params):
        response = self._post(method="waitinglist.query", **params)
        return response.get('result')

    def request(self, method, **arguments):
        return self._post(method=method, **arguments)

    def _post(self, **payload):
        logger.info("POST %s %s", config_ia_loan_api_url, payload)
        if config_ia_loan_api_developer_key:
            payload['developer'] = config_ia_loan_api_developer_key
        payload['token'] = config_ia_ol_shared_key

        try:
            jsontext = requests.post(
                config_ia_loan_api_url,
                data=payload,
                timeout=config_http_request_timeout,
            ).json()
            logger.info("POST response: %s", jsontext)
            return jsontext
        except Exception:  # TODO: Narrow exception scope
            logger.exception("POST failed")
            raise


ia_lending_api = IA_Lending_API()
