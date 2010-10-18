"""Handlers for borrowing books"""

import datetime, time
import hmac
import simplejson
import string
import urllib2

import web

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import public
from infogami.infobase.utils import parse_datetime

import utils
from utils import render_template

import acs4

########## Constants

lending_library_subject = 'Lending library'
loanstatus_url = config.get('loanstatus_url')

content_server = None

# Max loans a user can have at once
user_max_loans = 5

# When we generate a loan offer (.acsm) for a user we assume that the loan has occurred.
# Once the loan fulfillment inside Digital Editions the book status server will know
# the loan has occurred.  We allow this timeout so that we don't delete the OL loan
# record before fulfillment because we can't find it in the book status server.
# XXX If a user borrows an ACS4 book and immediately returns book loan will show as
#     "not yet downloaded" for the duration of the timeout.
#     BookReader loan status is always current.
loan_fulfillment_timeout_seconds = 60*5

# How long bookreader loans should last
bookreader_loan_seconds = 120 # XXXmang testing value

# How long the auth token given to the BookReader should last.  After the auth token
# expires the BookReader will not be able to access the book.  The BookReader polls
# OL periodically to get fresh tokens.
bookreader_auth_seconds = 10*60


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
            
        return render_template("borrow", edition, loans, False)
        
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
                
                raise web.seeother(loan_link)
            else:
                # Send to the borrow page
                raise web.seeother(error_redirect)
                
        elif i.action == 'return':
            # Check that this user has the loan
            user.update_loan_status()
            loans = get_loans(user)

            user_loan = None
            for loan in loans:
                if loan['user'] == user.key:
                    user_loan = loan
                    
            if not user_loan:
                # $$$ add error message
                raise web.seeother(error_redirect)
                
            # They have it -- return it
            return_resource(loan['resource_id'])
            
            # Get updated loans
            loans = get_loans(user)
            
            # Show the page with "you've just returned this"
            # $$$ we should call redirect here with some state saying the user just returned the book
            #     reloading the page will do the form post again which will do the redirect (no harm done)
            return render_template("borrow", edition, loans, True)
            
        else:
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
            
        return render_template("borrow_admin", edition, edition_loans, user_loans)
        
# Handler for /iauth/{itemid}
class ia_auth(delegate.page):
    path = r"/ia_auth/(.*)"
    
    def GET(self, item_id):
        i = web.input(_method='GET', callback=None)
        
        resource_id = 'bookreader:%s' % item_id
        content_type = "application/json"
        
        user = web.ctx.site.get_user()
        auth_json = simplejson.dumps( get_ia_auth_dict(user, resource_id) )
        
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
    global lending_library_subject
    
    # Check if in overdrive
    # $$$ Should we also require to be in lending library?
    if overdrive_id(edition):
        return True
    
    # Check that work is in lending library
    inLendingLibrary = False
    for work in edition.get('works', []):
        subjects = work.get_subjects()
        if subjects:
            try:
                if subjects.index(lending_library_subject) >= 0:
                    inLendingLibrary = True
                    break
            except ValueError:
                pass
                
    if not inLendingLibrary:
        return False
    
    # Book is in lending library
    
    # Check if hosted at archive.org
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
    """Returns true if this resource can be returned from the OL site"""
    if resource_type.startswith('bookreader'):
        return True
    return False
        
########## Helper Functions

def get_all_loans():
    return web.ctx.site.store.values(type='/type/loan')

def get_loans(user):
    return web.ctx.site.store.values(type='/type/loan', name='user', value=user.key)

def get_edition_loans(edition):
    return web.ctx.site.store.values(type='/type/loan', name='book', value=edition.key)
    
def get_loan_link(edition, type):
    """Get the loan link, which may be an ACS4 link or BookReader link depending on the loan type"""
    global content_server

    resource_id = edition.get_lending_resource_id(type)
    
    if type == 'bookreader':
        # link to bookreader
        return (resource_id, get_bookreader_link(edition))
        
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
    
def get_bookreader_link(edition):
    return "http://www.archive.org/stream/%s" % (edition.ocaid)
    
def get_loan_key(resource_id):
    """Get the key for the loan associated with the resource_id"""
    # Find loan in OL
    loan_keys = web.ctx.site.store.query('/type/loan', 'resource_id', resource_id)
    if not loan_keys:
        # No local records
        return

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
    
    # Get all Open Library loan records
    # $$$ Would be nice if there were a version of store.query that returned values as well as keys
    offset = 0
    limit = 500
    all_updated = False

    # Get book status records of everything loaned out
    bss_statuses = get_all_loaned_out()
    bss_resource_ids = [status['resourceid'] for status in bss_statuses]

    while not all_updated:
        ol_loan_keys = [row['key'] for row in web.ctx.site.store.query('/type/loan', limit=limit, offset=offset)]
        
        # Update status of each loan
        for loan_key in ol_loan_keys:
            loan = web.ctx.site.store.get(loan_key)
            try:
                status = bss_statuses[ bss_resource_ids.index(loan['resource_id']) ]
            except ValueError:
                status = None
                
            update_loan_from_bss_status(loan_key, loan, status)
        
        if len(ol_loan_keys) < limit:
            all_updated = True
        else:        
            offset += len(ol_loan_keys)

def user_can_borrow_edition(user, edition, type):
    """Returns true if the user can borrow this edition given their current loans.  Returns False if the
       user holds a current loan for the edition."""
       
    global user_max_loans
        
    if not can_borrow(edition):
        return False
    if user.get_loan_count() >= user_max_loans:
        return False
    
    if type in [loan['type'] for loan in edition.get_available_loans()]:
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

def get_ia_auth_dict(user, resource_id):
    """Returns response similar to one of these:
    {'success':true,'token':'1287185207-fa72103dd21073add8f87a5ad8bce845'}
    {'success':false,'msg':'Book is checked out'}
    """
    
    error_message = None
    
    # Lookup loan information
    loan_key = get_loan_key(resource_id)

    if not resource_id.startswith('bookreader'):
        error_message = 'Bad resource id type'
    
    elif not user:
        error_message = 'Not logged into Open Library'
    
    elif not loan_key:
        error_message = 'This book has not been checked out'
    
    else:
        # There is a loan for this book
        loan = web.ctx.site.store.get(loan_key)
        
        if loan['user'] != user.key:
            error_message = 'This books was not checked out by you'
        
        elif loan['expiry'] < datetime.datetime.utcnow().isoformat():
            error_message = 'Your loan has expired'
    
    if error_message:
        return { 'success': False, 'msg': error_message }
    
    item_id = resource_id[len('bookreader:'):]
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

########## Classes

class Loan:

    def __init__(self, user_key, book_key, resource_type, loaned_at = None):
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
        return '%s-%s-%s' % (self.user_key, self.book_key, self.resource_type)
        
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
        
    def load(self):
        self.set_dict(web.ctx.site.store[self.get_key()])
        
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
