"""Module for providing core functionality of lending on Open Library.
"""
import web
import simplejson
import datetime
import time
import logging
import uuid
import hmac
import urllib
import urllib2
from openlibrary.accounts.model import OpenLibraryAccount
from openlibrary.plugins.upstream import acs4
from . import ia
from . import msgbroker
from . import helpers as h

logger = logging.getLogger(__name__)

# How long bookreader loans should last
BOOKREADER_LOAN_DAYS = 14
BOOKREADER_STREAM_URL_PATTERN = "https://{0}/stream/{1}"

# How long the auth token given to the BookReader should last.  After the auth token
# expires the BookReader will not be able to access the book.  The BookReader polls
# OL periodically to get fresh tokens.
BOOKREADER_AUTH_SECONDS = 10*60


# When we generate a loan offer (.acsm) for a user we assume that the loan has occurred.
# Once the loan fulfillment inside Digital Editions the book status server will know
# the loan has occurred.  We allow this timeout so that we don't delete the OL loan
# record before fulfillment because we can't find it in the book status server.
# $$$ If a user borrows an ACS4 book and immediately returns book loan will show as
#     "not yet downloaded" for the duration of the timeout.
#     BookReader loan status is always current.
LOAN_FULFILLMENT_TIMEOUT_SECONDS = 60*5

config_ia_loan_api_url = None
config_ia_xauth_api_url = None
config_ia_availability_api_url = None
config_ia_access_secret = None
config_ia_ol_shared_key = None
config_ia_ol_xauth_s3 = None
config_ia_auth_only = None
config_http_request_timeout = None
config_content_server = None
config_loanstatus_url = None
config_bookreader_host = None
config_internal_tests_api_key = None

def setup(config):
    """Initializes this module from openlibrary config.
    """
    global config_content_server, config_loanstatus_url, \
        config_ia_access_secret, config_bookreader_host, \
        config_ia_ol_shared_key, config_ia_ol_xauth_s3, \
        config_internal_tests_api_key, config_ia_loan_api_url, \
        config_ia_availability_api_url, config_ia_xauth_api_url, \
        config_http_request_timeout, config_ia_auth_only

    if config.get("content_server"):
        try:
            config_content_server = ContentServer(config.get("content_server"))
        except Exception as e:
            logger.exception('Failed to assign config_content_server')
    else:
        logger.error('content_server unassigned')

    _ia_auth_only = False
    if config.get('ia_auth_only'):
        try:
            _ia_auth_only = bool(int(config.get('ia_auth_only')))
        except:
            logger.exception('Invalid value for ia_auth_only -- should be int 1 or 0')

    config_loanstatus_url = config.get('loanstatus_url')
    config_bookreader_host = config.get('bookreader_host', 'archive.org')
    config_ia_loan_api_url = config.get('ia_loan_api_url')
    config_ia_availability_api_url = config.get('ia_availability_api_url')
    config_ia_xauth_api_url = config.get('ia_xauth_api_url')
    config_ia_access_secret = config.get('ia_access_secret')
    config_ia_ol_shared_key = config.get('ia_ol_shared_key')
    config_ia_ol_auth_key = config.get('ia_ol_auth_key')
    config_ia_ol_xauth_s3 = config.get('ia_ol_xauth_s3')
    config_internal_tests_api_key = config.get('internal_tests_api_key')
    config_http_request_timeout = config.get('http_request_timeout')
    config_ia_auth_only = False or _ia_auth_only

def is_borrowable(identifiers, acs=False, restricted=False):
    """Takes a list of archive.org ocaids and returns json indicating
    whether each of these books represented by these identifiers are
    available (i.e. not on waiting list and not checked out via
    bookreader. Does not check acs4 (by default) because the queries
    are prohibitively slow.

    params:
        identifiers (list) - ocaids; Internet Archive item identifiers
        acs (int) - do a check to mark acs loans as unavailable
        restricted (int) - flag book is apart of a restricted collection

    """
    _acs = '1' if acs else '0'
    _restricted = '1' if restricted else '0'
    url = (config_ia_availability_api_url + '?action=availability&exact=%s&validate=%s'
           % (_acs, _restricted))
    data = urllib.urlencode({
        'identifiers': ','.join(identifiers)
    })
    try:
        content = urllib2.urlopen(
            url=url, data=data, timeout=config_http_request_timeout).read()
        return simplejson.loads(content).get('responses', {})
    except Exception as e:
        return {'error': 'request_timeout'}


def is_loaned_out(identifier):
    """Returns True if the given identifier is loaned out.

    This doesn't worry about waiting lists.
    """
    return (is_loaned_out_on_ol(identifier) or is_loaned_out_on_acs4(identifier)
            or is_loaned_out_on_ia(identifier))


def is_loaned_out_on_acs4(identifier):
    """Returns True if the item is checked out on acs4 server.
    """
    item = ACS4Item(identifier)
    return item.has_loan()


def is_loaned_out_on_ia(identifier):
    """Returns True if the item is checked out on Internet Archive.
    """
    url = "https://archive.org/services/borrow/%s?action=status" % identifier
    response = simplejson.loads(urllib2.urlopen(url).read())
    return response and response.get('checkedout')


def is_loaned_out_on_ol(identifier):
    """Returns True if the item is checked out on Open Library.
    """
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
    if d and (user_key is None or (d['user'] == account.username) or \
              (d['user'] == account.itemname)):
        loan = Loan(d)
        if loan.is_expired():
            return loan.delete()
    try:
        _loan = _get_ia_loan(identifier, account and userkey2userid(account.username))
    except Exception as e:
        pass

    try:
        _loan = _get_ia_loan(identifier, account and account.itemname)
    except Exception as e:
        pass

    return _loan


def _get_ia_loan(identifier, userid):
    ia_loan = ia_lending_api.get_loan(identifier, userid)
    return ia_loan and Loan.from_ia_loan(ia_loan)

def get_loans_of_user(user_key):
    """TODO: Remove inclusion of local data; should only come from IA"""
    account = OpenLibraryAccount.get(username=user_key.split('/')[-1])

    loandata = web.ctx.site.store.values(type='/type/loan', name='user', value=user_key)
    loans = [Loan(d) for d in loandata] + (_get_ia_loans_of_user(account.itemname) +
                                           _get_ia_loans_of_user(userkey2userid(user_key)))
    return loans

def _get_ia_loans_of_user(userid):
    ia_loans = ia_lending_api.find_loans(userid=userid)
    return [Loan.from_ia_loan(d) for d in ia_loans]

def create_loan(identifier, resource_type, user_key, book_key=None):
    """Creates a loan and returns it.
    """
    if config_content_server is None:
        raise Exception("the lending module is not initialized. Please call lending.setup function first.")

    ia_loan = ia_lending_api.create_loan(
         identifier=identifier,
         format=resource_type,
         userid=user_key,
         ol_key=book_key)

    if ia_loan:
        loan = Loan.from_ia_loan(ia_loan)
        msgbroker.send_message("loan-created", loan)
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

    ## XXX-Anand: Disabled as this seems to be going in recursive loop.
    ## IA calling OL hook and OL calling IA back.

    ## update the loan and waiting lists on archive.org
    # ia_lending_api.request(method="loan.sync", identifier=identifier)

    if loan is NOT_INITIALIZED:
        loan = get_loan(identifier)

    # The data of the loan without the user info.
    loan_data = loan and dict(
        uuid=loan['uuid'],
        loaned_at=loan['loaned_at'],
        resource_type=loan['resource_type'],
        ocaid=loan['ocaid'],
        book=loan['book'])

    try:
        wl = ia_lending_api.get_waitinglist_of_book(identifier)
    except urllib2.URLError:
        pass
    if wl is None:
        logger.error("failed to get waitinglist for %s", identifier, exc_info=True)
        return

    # for the end user, a book is not available if it is either
    # checked out or someone is waiting.
    borrowed = bool(is_loaned_out(identifier) or wl)

    ebook = EBookRecord.find(identifier)
    # The loan known to us is deleted
    is_loan_completed = ebook.get("loan") and ebook.get("loan") != loan_data

    # When the current loan is a OL loan, remember the loan_data
    if loan and loan.is_ol_loan():
        ebook_loan_data = loan_data
    else:
        ebook_loan_data = None

    try:
        ebook.update(
            type="ebook",
            identifier=identifier,
            loan=ebook_loan_data,
            borrowed=str(borrowed).lower(),
            wl_size=len(wl))
    except Exception:
        # updating ebook document is sometimes failing with
        # "Document update conflict" error.
        # Log the error in such cases, don't crash.
        logger.error("failed to update ebook for %s", identifier, exc_info=True)

    # fire loan-completed event
    if is_loan_completed and ebook.get('loan'):
        _d = dict(ebook['loan'], returned_at=time.time())
        msgbroker.send_message("loan-completed", _d)
    logger.info("END sync_loan %s", identifier)


class EBookRecord(dict):
    @staticmethod
    def find(identifier):
        key ="ebooks/" + identifier
        d = web.ctx.site.store.get(key) or {"_key": key, "type": "ebook", "_rev": 1}
        return EBookRecord(d)

    def update(self, **kwargs):
        logger.info("updating %s %s", self['_key'], kwargs)
        # Nothing to update if what we have is same as what is being asked to
        # update.
        d = dict((k, self.get(k)) for k in kwargs)
        if d == kwargs:
            return

        dict.update(self, **kwargs)
        web.ctx.site.store[self['_key']] = self


class Loan(dict):
    """Model for loan.
    """
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
            loan_link = BOOKREADER_STREAM_URL_PATTERN.format(config_bookreader_host, identifier)
            t_expiry = datetime.datetime.utcnow() + datetime.timedelta(days=BOOKREADER_LOAN_DAYS)
            expiry = t_expiry.isoformat()
        else:
            resource_id = get_resource_id(identifier, resource_type)
            loan_link = config_content_server.get_loan_link(resource_id)
            expiry = None

        if not resource_id:
            raise Exception('Could not find resource_id for %s - %s' % (identifier, resource_type))

        key = "loan-" + identifier
        return Loan({
            '_key': key,
            '_rev': 1,
            'type': '/type/loan',
            'user': user_key,
            'book': book_key,
            'ocaid': identifier,
            'expiry': expiry,
            'uuid': _uuid,
            'loaned_at': loaned_at,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'loan_link': loan_link,
        })

    @staticmethod
    def from_ia_loan(data):
        if data['userid'].startswith('ol:'):
            user_key = '/people/' + data['userid'][len('ol:'):]
        elif data['userid'].startswith('@'):
            account = OpenLibraryAccount.get_by_link(data['userid'])
            user_key = '/people/' + account.username
        else:
            user_key = None

        if data['ol_key']:
            book_key = data['ol_key']
        else:
            book_key = resolve_identifier(data['identifier'])

        created = h.parse_datetime(data['created'])

        # For historic reasons, OL considers expiry == None as un-fulfilled
        # loan.
        if data['fulfilled']:
            expiry = data['until']
        else:
            expiry = None

        d = {
            '_key': "loan-{0}".format(data['identifier']),
            '_rev': 1,
            'type': '/type/loan',
            'userid': data['userid'],
            'user': user_key,
            'book': book_key,
            'ocaid': data['identifier'],
            'expiry': expiry,
            'fulfilled': data['fulfilled'],
            'uuid': 'loan-{0}'.format(data['id']),
            'loaned_at': time.mktime(created.timetuple()),
            'resource_type': data['format'],
            'resource_id': data['resource_id'],
            'loan_link': data['loan_link'],
            'stored_at': 'ia'
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

        # Inform listers that a loan is creted/updated
        msgbroker.send_message("loan-created", self)

    def is_expired(self):
        return self['expiry'] and self['expiry'] < datetime.datetime.utcnow().isoformat()

    def is_yet_to_be_fulfilled(self):
        """Returns True if the loan is not yet fulfilled and fulfillment time
        is not expired.
        """
        return (self['expiry'] is None and
                (time.time() - self['loaned_at']) < LOAN_FULFILLMENT_TIMEOUT_SECONDS)

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
        msgbroker.send_message("loan-completed", loan)

def resolve_identifier(identifier):
    """Returns the OL book key for given IA identifier.
    """
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

def make_ia_token(item_id, expiry_seconds):
    """Make a key that allows a client to access the item on archive.org for the number of
       seconds from now.
    """
    access_key = config_ia_access_secret
    if access_key is None:
        raise Exception("config value config.ia_access_secret is not present -- check your config")

    timestamp = int(time.time() + expiry_seconds)
    token_data = '%s-%d' % (item_id, timestamp)

    token = '%d-%s' % (timestamp, hmac.new(access_key, token_data).hexdigest())
    return token


def make_bookreader_auth_link(loan_key, item_id, book_path, ol_host):
    """
    Generate a link to BookReaderAuth.php that starts the BookReader with the information to initiate reading
    a borrowed book
    """

    access_token = make_ia_token(item_id, BOOKREADER_AUTH_SECONDS)
    auth_url = 'https://%s/bookreader/BookReaderAuth.php?uuid=%s&token=%s&id=%s&bookPath=%s&olHost=%s' % (
        config_bookreader_host, loan_key, access_token, item_id, book_path, ol_host
    )

    return auth_url

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
            logger.info("%s: loan returned or expired or timedout, deleting...", identifier)
            loan.delete()
            return

        if loan['expiry'] != acs4_loan['until']:
            loan['expiry'] = acs4_loan['until']
            loan.save()
            logger.info("%s: updated expiry to %s", identifier, loan['expiry'])

class ContentServer:
    """Connection to ACS4 content server and book status.
    """
    def __init__(self, config):
        self.host = config.host
        self.port = config.port
        self.password = config.password
        self.distributor = config.distributor

        # Contact server to get shared secret for signing
        result = acs4.get_distributor_info(self.host, self.password, self.distributor)
        self.shared_secret = result['sharedSecret']
        self.name = result['name']

    def get_loan_link(self, resource_id):
        loan_link = acs4.mint(self.host, self.shared_secret, resource_id, 'enterloan', self.name, port = self.port)
        return loan_link


class ACS4Item(object):
    """Represents an item on ACS4 server.

    An item can have multiple resources (epub/pdf) and any of them could be loanded out.

    This class provides a way to access the loan info from ACS4 server.
    """
    def __init__(self, identifier):
        self.identifier = identifier

    def get_data(self):
        url = '%s/item/%s' % (config_loanstatus_url, self.identifier)
        try:
            return simplejson.loads(urllib2.urlopen(url).read())
        except IOError:
            logger.error("unable to conact BSS server", exc_info=True)

    def has_loan(self):
        return bool(self.get_loan())

    def get_loan(self):
        """Returns the information about loan in the ACS4 server.
        """
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
        formats = {
            "application/epub+zip": "epub",
            "application/pdf": "pdf"
        }
        return formats[format]


class IA_Lending_API:
    """Archive.org waiting list API.
    """
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
        response = self._post(method="loan.create", identifier=identifier, userid=userid, format=format, ol_key=ol_key)
        if response['status'] == 'ok':
            return response['result']['loan']

    def delete_loan(self, identifier, userid):
        self._post(method="loan.delete", identifier=identifier, userid=userid)

    def get_waitinglist_of_book(self, identifier):
        return self.query(identifier=identifier)

    def get_waitinglist_of_user(self, userid):
        return self.query(userid=userid)

    def join_waitinglist(self, identifier, userid):
        return self._post(method="waitinglist.join",
                          identifier=identifier,
                          userid=userid)

    def leave_waitinglist(self, identifier, userid):
        return self._post(method="waitinglist.leave",
                          identifier=identifier,
                          userid=userid)

    def update_waitinglist(self, identifier, userid, **kwargs):
        return self._post(method="waitinglist.update",
                          identifier=identifier,
                          userid=userid,
                          **kwargs)

    def query(self, **params):
        response = self._post(method="waitinglist.query", **params)
        return response.get('result')

    def request(self, method, **arguments):
        return self._post(method=method, **arguments)

    def _post(self, **params):
        logger.info("POST %s %s", config_ia_loan_api_url, params)
        params['token'] = config_ia_ol_shared_key
        payload = urllib.urlencode(params)
        try:
            jsontext = urllib2.urlopen(config_ia_loan_api_url, payload,
                                       timeout=config_http_request_timeout).read()
            logger.info("POST response: %s", jsontext)
            return simplejson.loads(jsontext)
        except Exception as e:
            logger.exception("POST failed")
            raise

ia_lending_api = IA_Lending_API()
