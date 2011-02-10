"""Handlers for borrowing books"""

import copy
import datetime, time
import hmac
import re
import simplejson
import string
import urllib2
import uuid

import web

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import public
from infogami.infobase.utils import parse_datetime

import utils
from utils import render_template

from openlibrary.core import inlibrary

import acs4

########## Constants

lending_library_subject = u'Lending library'
in_library_subject = u'In library'
loanstatus_url = config.get('loanstatus_url')

content_server = None

# ACS4 resource ids start with 'urn:uuid:'.  The meta.xml on archive.org
# adds 'acs:epub:' or 'acs:pdf:' to distinguish the file type.
acs_resource_id_prefixes = ['urn:uuid:', 'acs:epub:', 'acs:pdf:']

# Max loans a user can have at once
user_max_loans = 5

# When we generate a loan offer (.acsm) for a user we assume that the loan has occurred.
# Once the loan fulfillment inside Digital Editions the book status server will know
# the loan has occurred.  We allow this timeout so that we don't delete the OL loan
# record before fulfillment because we can't find it in the book status server.
# $$$ If a user borrows an ACS4 book and immediately returns book loan will show as
#     "not yet downloaded" for the duration of the timeout.
#     BookReader loan status is always current.
loan_fulfillment_timeout_seconds = 60*5

# How long bookreader loans should last
bookreader_loan_seconds = 60*60*24*14

# How long the auth token given to the BookReader should last.  After the auth token
# expires the BookReader will not be able to access the book.  The BookReader polls
# OL periodically to get fresh tokens.
bookreader_auth_seconds = 10*60

# Base URL for BookReader
try:
    bookreader_host = config.bookreader_host
except AttributeError:
    bookreader_host = 'www.archive.org'
    
bookreader_stream_base = 'http://' + bookreader_host + '/stream'

########## Page Handlers

# Handler for /books/{bookid}/{title}/borrow
class borrow(delegate.page):
    path = "(/books/OL\d+M)/borrow"
    
    def GET(self, key):
        edition = web.ctx.site.get(key)
        
        if not edition:
            raise web.notfound()

        edition.update_loan_status()
            
        loans = []
        user = web.ctx.site.get_user()
        if user:
            user.update_loan_status()
            loans = get_loans(user)
        
        # Check if we recently did a return
        i = web.input(r=None)
        if i.r == 't':
            have_returned = True
        else:
            have_returned = False
        
        return render_template("borrow", edition, loans, have_returned)
        
    def POST(self, key):
        """Called when the user wants to borrow the edition"""
        
        i = web.input(action='borrow', format=None)
        
        edition = web.ctx.site.get(key)
        if not edition:
            raise web.notfound()
        error_redirect = edition.url("/borrow")
        
        user = web.ctx.site.get_user()
        if not user:
            raise web.seeother(error_redirect)

        if i.action == 'borrow':
            resource_type = i.format
            
            if resource_type not in ['epub', 'pdf', 'bookreader']:
                raise web.seeother(error_redirect)
            
            if user_can_borrow_edition(user, edition, resource_type):
                loan = Loan(user.key, key, resource_type)
                if resource_type == 'bookreader':
                    # The loan expiry should be utc isoformat
                    loan.expiry = datetime.datetime.utcfromtimestamp(time.time() + bookreader_loan_seconds).isoformat()
                loan_link = loan.make_offer() # generate the link and record that loan offer occurred
                
                # $$$ Record fact that user has done a borrow - how do I write into user? do I need permissions?
                # if not user.has_borrowed:
                #   user.has_borrowed = True
                #   user.save()
                
                if resource_type == 'bookreader':
                    raise web.seeother(make_bookreader_auth_link(loan.get_key(), edition.ocaid, '/stream/' + edition.ocaid))
                else:
                    raise web.seeother(loan_link)
            else:
                # Send to the borrow page
                raise web.seeother(error_redirect)
                
        elif i.action == 'return':
            # Check that this user has the loan
            user.update_loan_status()
            loans = get_loans(user)

            # We pick the first loan that the user has for this book that is returnable.
            # Assumes a user can't borrow multiple formats (resource_type) of the same book.
            user_loan = None
            for loan in loans:
                if loan['book'] == edition.key and can_return_resource_type(loan['resource_type']):
                    user_loan = loan
                    break
                    
            if not user_loan:
                # $$$ add error message
                raise web.seeother(error_redirect)
                
            # They have it -- return it
            return_resource(user_loan['resource_id'])
            
            # Get updated loans
            loans = get_loans(user)
            
            # Show the page with "you've returned this"
            # $$$ this would do better in a session variable that can be cleared
            #     after the message is shown once
            raise web.seeother(edition.url('/borrow?r=t'))
            
        elif i.action == 'read':
            # Look for loans for this book
            user.update_loan_status()
            loans = get_loans(user)
            for loan in loans:
                if loan['book'] == edition.key:
                    raise web.seeother(make_bookreader_auth_link(loan['store_key'], edition.ocaid, '/stream/' + edition.ocaid))
            
        # Action not recognized
        raise web.seeother(error_redirect)

class borrow_admin(delegate.page):
    path = "(/books/OL\d+M)/borrow_admin"
    
    def GET(self, key):
        if not is_admin():
            return render_template('permission_denied', web.ctx.path, "Permission denied.")
    
        edition = web.ctx.site.get(key)
        
        if not edition:
            raise web.notfound()

        edition.update_loan_status()
        edition_loans = get_edition_loans(edition)
            
        user_loans = []
        user = web.ctx.site.get_user()
        if user:
            user.update_loan_status()
            user_loans = get_loans(user)
            
        return render_template("borrow_admin", edition, edition_loans, user_loans, web.ctx.ip)
        
# Handler for /iauth/{itemid}
class ia_auth(delegate.page):
    path = r"/ia_auth/(.*)"
    
    def GET(self, item_id):
        i = web.input(_method='GET', callback=None, loan=None, token=None)
        
        resource_id = 'bookreader:%s' % item_id
        content_type = "application/json"
        
        # check that identifier is valid
        
        user = web.ctx.site.get_user()
        auth_json = simplejson.dumps( get_ia_auth_dict(user, item_id, resource_id, i.loan, i.token ) )
                
        output = auth_json
        
        if i.callback:
            content_type = "text/javascript"
            output = '%s ( %s );' % (i.callback, output)
        
        return delegate.RawText(output, content_type=content_type)
        
########## Public Functions

@public
def overdrive_id(edition):
    identifier = None
    if edition.get('identifiers', None) and edition.identifiers.get('overdrive', None):
        identifier = edition.identifiers.overdrive[0]
    return identifier

@public
def can_borrow(edition):
    global lending_library_subject, in_library_subject
    
    # Check if in overdrive
    # $$$ Should we also require to be in lending library?
    if overdrive_id(edition):
        return True
    
    # Check that work is in the general lending library, or available for
    # in-library loan and the user is in a library
    lendable = False
    for work in edition.get('works', []):
        subjects = work.get_subjects()
        
        if subjects:
            if lending_library_subject in subjects:
                # General lending library
                lendable = True
                break
            if in_library_subject in subjects:
                # Books is eligible for in-library loan
                if 'inlibrary' in web.ctx.features and inlibrary.get_library() is not None:
                    # Person is in a library
                    lendable = True
                    break
                        
    if not lendable:
        return False
    
    # Check if hosted at archive.org - sanity check
    if edition.get('ocaid', False):
        return True
    
    return False

@public
def is_loan_available(edition, type):    
    resource_id = edition.get_lending_resource_id(type)
    
    if not resource_id:
        return False
        
    return not is_loaned_out(resource_id)

@public
def datetime_from_isoformat(expiry):
    """Returns datetime object, or None"""
    if expiry is None:
        return None
    return parse_datetime(expiry)
        
@public
def datetime_from_utc_timestamp(seconds):
    return datetime.datetime.utcfromtimestamp(seconds)

@public
def can_return_resource_type(resource_type):
    """Returns true if this resource can be returned from the OL site."""
    if resource_type.startswith('bookreader'):
        return True
    return False
    
@public
def ia_identifier_is_valid(item_id):
    """Returns false if the item id is obviously malformed. Not currently checking length."""
    if re.match(r'^[a-zA-Z0-9][a-zA-Z0-9\.\-_]*$', item_id):
        return True
    return False
    
@public
def get_bookreader_stream_url(itemid):
    return bookreader_stream_base + '/' + itemid
    
@public
def get_bookreader_host():
    return bookreader_host
    
        
########## Helper Functions

def get_all_store_values(**query):
    """Get all values by paging through all results. Note: adds store_key with the row id."""
    query = copy.deepcopy(query)
    if not query.has_key('limit'):
        query['limit'] = 500
    query['offset'] = 0
    values = []
    got_all = False
    
    while not got_all:
        #new_values = web.ctx.site.store.values(**query)
        new_items = web.ctx.site.store.items(**query)
        for new_item in new_items:
            new_item[1].update({'store_key': new_item[0]})
            values.append(new_item[1])
        if len(new_items) < query['limit']:
            got_all = True
        query['offset'] += len(new_items)
    return values

def get_all_loans():
    # return web.ctx.site.store.values(type='/type/loan')
    return get_all_store_values(type='/type/loan')

def get_loans(user):
    # return web.ctx.site.store.values(type='/type/loan', name='user', value=user.key)
    return get_all_store_values(type='/type/loan', name='user', value=user.key)    

def get_edition_loans(edition):
    # return web.ctx.site.store.values(type='/type/loan', name='book', value=edition.key)
    return get_all_store_values(type='/type/loan', name='book', value=edition.key)

    
def get_loan_link(edition, type):
    """Get the loan link, which may be an ACS4 link or BookReader link depending on the loan type"""
    global content_server

    resource_id = edition.get_lending_resource_id(type)
    
    if type == 'bookreader':
        # link to bookreader
        return (resource_id, get_bookreader_stream_url(edition.ocaid))
        
    if type in ['pdf','epub']:
        # ACS4
        if not content_server:
            if not config.content_server:
                # $$$ log
                return None
            content_server = ContentServer(config.content_server)
            
        if not resource_id:
            raise Exception('Could not find resource_id for %s - %s' % (edition.key, type))
        return (resource_id, content_server.get_loan_link(resource_id))
        
    raise Exception('Unknown resource type %s for loan of edition %s', edition.key, type)
    
# def get_bookreader_link(edition):
#     """Returns the link to the BookReader for the edition"""
#     return "%s/%s" % (bookreader_stream_base, edition.ocaid)
    
def get_loan_key(resource_id):
    """Get the key for the loan associated with the resource_id"""
    # Find loan in OL
    loan_keys = web.ctx.site.store.query('/type/loan', 'resource_id', resource_id)
    if not loan_keys:
        # No local records
        return None

    # Only support single loan of resource at the moment
    if len(loan_keys) > 1:
        raise Exception('Found too many local loan records for resource %s' % resource_id)
        
    loan_key = loan_keys[0]['key']
    return loan_key    
    
def get_loan_status(resource_id):
    """Should only be used for ACS4 loans.  Get the status of the loan from the ACS4 server,
       via the Book Status Server (BSS)
    """
    global loanstatus_url
    
    if not loanstatus_url:
        raise Exception('No loanstatus_url -- cannot check loan status')
    
    # BSS response looks like this:
    #
    # [
    #     {
    #         "loanuntil": "2010-06-25T00:52:04", 
    #         "resourceid": "a8b600e2-32fd-4aeb-a2b5-641103583254", 
    #         "returned": "F", 
    #         "until": "2010-06-25T00:52:04"
    #     }
    # ]

    url = '%s/is_loaned_out/%s' % (loanstatus_url, resource_id)
    try:
        response = simplejson.loads(urllib2.urlopen(url).read())
        if len(response) == 0:
            # No outstanding loans
            return None
        
        else:
            return response[0]
            
    except IOError:
        # status server is down
        # $$$ be more graceful
        raise Exception('Loan status server not available - tried at %s', url)
    
    raise Exception('Error communicating with loan status server for resource %s' % resource_id)

def get_all_loaned_out():
    """Returns array of BSS status for all resources currently loaned out (according to BSS)"""
    global loanstatus_url
    
    if not loanstatus_url:
        raise Exception('No loanstatus_url -- cannot check loan status')
        
    url = '%s/is_loaned_out/' % loanstatus_url
    try:
        response = simplejson.loads(urllib2.urlopen(url).read())
        return response
    except IOError:
        raise Exception('Loan status server not available')

def is_loaned_out(resource_id):

    # bookreader loan status is stored in the private data store
    if resource_id.startswith('bookreader'):
        # Check our local status
        loan_key = get_loan_key(resource_id)
        if not loan_key:
            # No loan recorded
            return False

        # Find the loan and check if it has expired
        loan = web.ctx.store.get(loan_key)
        if loan:
            if datetime_from_isoformat(loan['expiry']) < datetime.datetime.utcnow():
                return True
                
        return False
    
    # Assume ACS4 loan - check status server
    status = get_loan_status(resource_id)
    return is_loaned_out_from_status(status)
    
def is_loaned_out_from_status(status):
    if not status:
        return False
    else:
        if status['returned'] == 'T':
            # Current loan has been returned
            return False
            
    # Has status and not returned
    return True
    
def update_loan_status(resource_id):
    """Update the loan status in OL based off status in ACS4.  Used to check for early returns."""
    
    # Get local loan record
    loan_key = get_loan_key(resource_id)
    
    if not loan_key:
        # No loan recorded, nothing to do
        return
        
    loan = web.ctx.site.store.get(loan_key)
    
    # If this is a BookReader loan, local version of loan is authoritative
    if loan['resource_type'] == 'bookreader':
        # delete loan record if has expired
        # $$$ consolidate logic for checking expiry.  keep loan record for some time after it expires.
        if loan['expiry'] and loan['expiry'] < datetime.datetime.utcnow().isoformat():
            web.ctx.site.store.delete(loan_key)
        return
        
    # Load status from book status server
    status = get_loan_status(resource_id)

    update_loan_from_bss_status(loan_key, loan, status)
        
def update_loan_from_bss_status(loan_key, loan, status):
    """Update the loan status in the private data store from BSS status"""
    
    global loan_fulfillment_timeout_seconds
    
    if not resource_uses_bss(loan['resource_id']):
        raise Exception('Tried to update loan %s with ACS4/BSS status when it should not use BSS' % loan_key)
    
    if not is_loaned_out_from_status(status):
        # No loan record, or returned or expired
        
        # Check if our local loan record is fresh -- allow some time for fulfillment
        if loan['expiry'] is None:
            now = time.time()
            # $$$ loan_at in the store is in timestamp seconds until updated (from BSS) to isoformat string
            if now - loan['loaned_at'] < loan_fulfillment_timeout_seconds:
                # Don't delete the loan record - give it time to complete
                return
    
        # Was returned, expired, or timed out
        web.ctx.site.store.delete(loan_key)
        return

    # Book has non-returned status
    # Update expiry
    if loan['expiry'] != status['until']:
        loan['expiry'] = status['until']
        web.ctx.site.store[loan_key] = loan

def update_all_loan_status():
    """Update the status of all loans known to Open Library by cross-checking with the book status server"""
    
    # Get book status records of everything loaned out
    bss_statuses = get_all_loaned_out()
    bss_resource_ids = [status['resourceid'] for status in bss_statuses]

    for resource_type in ['epub', 'pdf']:
        # print "updating %s loans" % resource_type
        
        offset = 0
        limit = 500
        all_updated = False
    
        while not all_updated:
            # Could just get epub and pdf loans here since they're the ones that use BSS
            ol_loan_keys = [row['key'] for row in web.ctx.site.store.query('/type/loan', 'resource_type', resource_type, limit=limit, offset=offset)]
            
            # Update status of each loan
            for loan_key in ol_loan_keys:
                loan = web.ctx.site.store.get(loan_key)
                
                if resource_uses_bss(loan['resource_id']):
                    try:
                        status = bss_statuses[ bss_resource_ids.index(loan['resource_id']) ]
                    except ValueError:
                        status = None
                        
                    update_loan_from_bss_status(loan_key, loan, status)
            
            if len(ol_loan_keys) < limit:
                all_updated = True
            else:        
                offset += len(ol_loan_keys)
            
def resource_uses_bss(resource_id):
    """Returns true if the resource should use the BSS for status"""
    global acs_resource_id_prefixes
    
    if resource_id:
        for prefix in acs_resource_id_prefixes:
            if resource_id.startswith(prefix):
                return True
    return False

def user_can_borrow_edition(user, edition, type):
    """Returns true if the user can borrow this edition given their current loans.  Returns False if the
       user holds a current loan for the edition."""
       
    global user_max_loans
        
    if not can_borrow(edition):
        return False
    if user.get_loan_count() >= user_max_loans:
        return False
    
    if type in [loan['resource_type'] for loan in edition.get_available_loans()]:
        return True
    
    return False

def is_admin():
    """"Returns True if the current user is in admin usergroup."""
    user = web.ctx.site.get_user()
    return user and user.key in [m.key for m in web.ctx.site.get('/usergroup/admin').members]
    
def return_resource(resource_id):
    """Return the book to circulation!  This object is invalid and should not be used after
       this is called.  Currently only possible for bookreader loans."""
    loan_key = get_loan_key(resource_id)
    if not loan_key:
        raise Exception('Asked to return %s but no loan recorded' % resource_id)
    
    loan = web.ctx.site.store.get(loan_key)
    if loan['resource_type'] != 'bookreader':
        raise Exception('Not possible to return loan %s of type %s' % (loan['resource_id'], loan['resource_type']))
    # $$$ Could add some stats tracking.  For now we just nuke it.
    web.ctx.site.store.delete(loan_key)

def get_ia_auth_dict(user, item_id, resource_id, user_specified_loan_key, access_token):
    """Returns response similar to one of these:
    {'success':true,'token':'1287185207-fa72103dd21073add8f87a5ad8bce845','borrowed':true}
    {'success':false,'msg':'Book is checked out','borrowed':false, 'resolution': 'You can visit <a href="http://openlibary.org/ia/someid">this book\'s page on Open Library</a>.'}
    """
    
    base_url = 'http://' + web.ctx.host
    resolution_dict = { 'base_url': base_url, 'item_id': item_id }
    
    error_message = None
    user_has_current_loan = False
    
    # Sanity checks
    if not ia_identifier_is_valid(item_id):
        return {'success': False, 'msg': 'Invalid item id', 'resolution': 'This book does not appear to have a valid item identifier.' }

    if not resource_id.startswith('bookreader'):
        error_message = 'Bad resource id type'
        resolution_message = 'This book cannot be borrowed for in-browser loan. You can <a href="%(base_url)s/ia/%(item_id)s">visit this book\'s page</a> on openlibrary.org to learn more about the book.' % resolution_dict
        return {'success': False, 'msg': error_message, 'resolution': resolution_message }
    
    # Lookup loan information
    loan_key = get_loan_key(resource_id)

    if loan_key is None:
        # Book is not checked out as a BookReader loan - may still be checked out in ACS4
        error_message = 'Lending Library Book'
        resolution_message = 'This book is part of the <a href="%(base_url)s/subjects/Lending_library">lending library</a>. Please <a href="%(base_url)s/ia/%(item_id)s/borrow">visit this book\'s page on Open Library</a> to access the book.' % resolution_dict
        
    else:
        # Book is checked out (by someone) - get the loan information
        loan = web.ctx.site.store.get(loan_key)
        
        # Check that this is a bookreader loan
        if loan['resource_type'] != 'bookreader':
            error_message = 'No BookReader loan'
            resolution_message = 'This book was borrowed as ' + loan['resource_type'] + '. You can <a href="%(base_url)s/ia/%(item_id)s">visit this book\'s page</a> on openlibrary.org to access the book in that format.' % resolution_dict
            return {'success': False, 'msg': error_message, 'resolution': resolution_message }
        
        # If we know who this user is, from third-party cookies and they are logged into openlibrary.org, check if they have the loan
        if user:
            if loan['user'] != user.key:
                # Borrowed by someone else
                error_message = 'This book is checked out'
                resolution_message = 'This book is currently checked out.  You can <a href="%(base_url)s/ia/%(item_id)s">visit this book\'s page on Open Library</a> or <a href="%(base_url)s/subjects/Lending_library">look at other books available to borrow</a>.' % resolution_dict
            
            elif loan['expiry'] < datetime.datetime.utcnow().isoformat():
                # User has the loan, but it's expired
                error_message = 'Your loan has expired'
                resolution_message = 'Your loan for this book has expired.  You can <a href="%(base_url)s/ia/%(item_id)s">visit this book\'s page on Open Library</a>.' % resolution_dict
            
            else:
                # User holds the loan - win!
                user_has_current_loan = True
        else:
            # Don't have user context - not logged in or third-party cookies disabled
            
            # Check if the loan id + token is valid
            if user_specified_loan_key and access_token and ia_token_is_current(item_id, access_token):
                # Win!
                user_has_current_loan = True
                    
            else:
                # Couldn't validate using token - they need to go to Open Library
                error_message = "Lending Library Book"
                resolution_message = 'This book is part of the <a href="%(base_url)s/subjects/Lending_library" title="Open Library Lending Library">lending library</a>. Please <a href="%(base_url)s/ia/%(item_id)s/borrow" title="Borrow book page on Open Library">visit this book\'s page on Open Library</a> to access the book.  You must have cookies enabled for archive.org and openlibrary.org to access borrowed books.' % resolution_dict
    
    if error_message:
        return { 'success': False, 'msg': error_message, 'resolution': resolution_message }
    else:
        # No error message, make sure we thought the loan was current as sanity check
        if not user_has_current_loan:
            raise Exception('lending: no current loan for this user found but no error condition specified')
    
    return { 'success': True, 'token': make_ia_token(item_id, bookreader_auth_seconds) }
    

def make_ia_token(item_id, expiry_seconds):
    """Make a key that allows a client to access the item on archive.org for the number of
       seconds from now.
    """
    # $timestamp = $time+600; //access granted for ten minutes
    # $hmac = hash_hmac('md5', "{$id}-{$timestamp}", configGetValue('ol-loan-secret'));
    # return "{$timestamp}-{$hmac}";
    
    try:
        access_key = config.ia_access_secret
    except AttributeError:
        raise Exception("config value config.ia_access_secret is not present -- check your config")
        
    timestamp = int(time.time() + expiry_seconds)
    token_data = '%s-%d' % (item_id, timestamp)
    
    token = '%d-%s' % (timestamp, hmac.new(access_key, token_data).hexdigest())
    return token
    
def ia_token_is_current(item_id, access_token):
    try:
        access_key = config.ia_access_secret
    except AttributeError:
        raise Exception("config value config.ia_access_secret is not present -- check your config")
    
    # Check if token has expired
    try:
        token_timestamp = access_token.split('-')[0]
    except:
        return False
        
    token_time = int(token_timestamp)
    now = int(time.time())
    if token_time < now:
        return False
    
    # Verify token is valid
    try:
        token_hmac = access_token.split('-')[1]
    except:
        return False
        
    expected_data = '%s-%s' % (item_id, token_timestamp)
    expected_hmac = hmac.new(access_key, expected_data).hexdigest()
    
    if token_hmac == expected_hmac:
        return True
        
    return False
    
def make_bookreader_auth_link(loan_key, item_id, book_path):
    """
    Generate a link to BookReaderAuth.php that starts the BookReader with the information to initiate reading
    a borrowed book
    """
    
    access_token = make_ia_token(item_id, bookreader_auth_seconds)
    auth_url = 'http://%s/bookreader/BookReaderAuth.php?uuid=%s&token=%s&id=%s&bookPath=%s' % (
        bookreader_host, loan_key, access_token, item_id, book_path
    )
    return auth_url

########## Classes

class Loan:

    def __init__(self, user_key, book_key, resource_type, loaned_at = None):
        self.key = uuid.uuid4().hex
        self.user_key = user_key
        self.book_key = book_key
        self.resource_type = resource_type
        self.type = '/type/loan'
        self.resource_id = None
        self.loan_link = None
        self.expiry = None # We leave the expiry blank until we get confirmation of loan from ACS4
        
        if loaned_at is not None:
            self.loaned_at = loaned_at
        else:
            self.loaned_at = time.time()
        
    def get_key(self):
        #return '%s-%s-%s' % (self.user_key, self.book_key, self.resource_type)
        return self.key
        
    def get_dict(self):
        return { 'user': self.user_key, 'type': '/type/loan',
                 'book': self.book_key, 'expiry': self.expiry,
                 'loaned_at': self.loaned_at, 'resource_type': self.resource_type,
                 'resource_id': self.resource_id, 'loan_link': self.loan_link }
                 
    def set_dict(self, loan_dict):
        self.user_key = loan_dict['user']
        self.type = loan_dict['type']
        self.book_key = loan_dict['book']
        self.resource_type = loan_dict['resource_type']
        self.expiry = loan_dict['expiry']
        self.loaned_at = loan_dict['loaned_at']
        self.resource_id = loan_dict['resource_id']
        self.loan_link = loan_dict['loan_link']
        
    #def load(self):
    #    self.set_dict(web.ctx.site.store[self.get_key()])
        
    def save(self):
        web.ctx.site.store[self.get_key()] = self.get_dict()
        
    def remove(self):
        web.ctx.site.delete(self.get_key())
        
    def make_offer(self):
        """Create loan url and record that loan was offered.  Returns the link URL that triggers
           Digital Editions to open or the link for the BookReader."""
           
        edition = web.ctx.site.get(self.book_key)
        resource_id, loan_link = get_loan_link(edition, self.resource_type)
        if not loan_link:
            raise Exception('Could not get loan link for edition %s type %s' % self.book_key, self.resource_type)
        self.loan_link = loan_link
        self.resource_id = resource_id
        self.save()
        return self.loan_link
        
class ContentServer:
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
