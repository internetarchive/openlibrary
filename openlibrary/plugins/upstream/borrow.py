"""Handlers for borrowing books"""

import datetime, time
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
# XXX if user borrows and immediately returns book loan will show as "not yet downloaded"
#     for the duration of the timeout
loan_fulfillment_timeout_seconds = 60*5

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
            
        return render_template("borrow", edition, loans)
        
    def POST(self, key):
        i = web.input(format=None)
        resource_type = i.format
        
        edition = web.ctx.site.get(key)
        if not edition:
            raise web.notfound()
        error_redirect = edition.url("/borrow")
        
        user = web.ctx.site.get_user()
        if not user:
            raise web.seeother(error_redirect)
        
        if resource_type not in ['epub', 'pdf']:
            raise web.seeother(error_redirect)
        
        if user_can_borrow_edition(user, edition, resource_type):
            loan = Loan(user.key, key, resource_type)
            loan_link = loan.make_offer() # generate the link and record that loan offer occurred
            
            # XXX Record fact that user has done a borrow borrow - how do I write into user? do I need permissions?
            # if not user.has_borrowed:
            #   user.has_borrowed = True
            #   user.save()
            
            raise web.seeother(loan_link)
        else:
            # Send to the borrow page
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

########## Helper Functions

def get_all_loans():
    return web.ctx.site.store.values(type='/type/loan')

def get_loans(user):
    return web.ctx.site.store.values(type='/type/loan', name='user', value=user.key)

def get_edition_loans(edition):
    return web.ctx.site.store.values(type='/type/loan', name='book', value=edition.key)
    
def get_loan_link(edition, type):
    global content_server
    
    if not content_server:
        if not config.content_server:
            # $$$ log
            return None
        content_server = ContentServer(config.content_server)
        
    resource_id = edition.get_lending_resource_id(type)
    if not resource_id:
        raise Exception('Could not find resource_id for %s - %s' % (edition.key, type))
    return (resource_id, content_server.get_loan_link(resource_id))
    
def get_loan_status(resource_id):
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
        raise Exception('Loan status server not available')
    
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
    
    # Find loan in OL
    loan_keys = web.ctx.site.store.query('/type/loan', 'resource_id', resource_id)
    if not loan_keys:
        # No local records
        return

    # Only support single loan of resource at the moment
    if len(loan_keys) > 1:
        raise Exception('Found too many local loan records for resource %s' % resource_id)
        
    loan_key = loan_keys[0]['key']
        
    # Load status from book status server
    status = get_loan_status(resource_id)

    # Local loan record
    loan = web.ctx.site.store.get(loan_key)
    
    update_loan_from_bss_status(loan_key, loan, status)
        
def update_loan_from_bss_status(loan_key, loan, status):
    """Update the loan status in the private data store from BSS status"""
    
    global loan_fulfillment_timeout_seconds
    
    if not is_loaned_out_from_status(status):
        # No loan record, or returned or expired
        
        # Check if our local loan record is fresh -- allow some time for fulfillment
        if loan['expiry'] is None:
            now = time.time()
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
           Digital Editions to open."""
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
