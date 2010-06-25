"""Handlers for borrowing books"""

import datetime
import simplejson
import string
import urllib2

import web

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import public

import utils
from utils import render_template

import acs4

########## Constants

lending_library_subject = 'Lending library'
loanstatus_url = config.loanstatus_url

content_server = None

########## Page Handlers

# Handler for /books/{bookid}/{title}/borrow
class borrow(delegate.page):
    path = "(/books/OL\d+M)/borrow"
    
    def GET(self, key):
        edition = web.ctx.site.get(key)
        
        if not edition:
            raise web.notfound()
            
        loans = []
        user = web.ctx.site.get_user()
        if user:
            loans = get_loans(user)
            
        return render_template("borrow", edition, loans)
        
class do_borrow(delegate.page):
    """Actually borrow the book, via POST"""
    path = "(/books/OL\d+M)/_doborrow"
    
    def POST(self, key):
        i = web.input()
        
        user = web.ctx.site.get_user()
        
        everythingChecksOut = True # XXX
        if everythingChecksOut:
            # XXX get loan URL and loan id            
            resourceType = 'epub'
            loan = Loan(user.key, key, resourceType)
            loan.add()
            acs4link = loan.create_url()
            raise web.seeother(acs4link)
        else:
            # Send to the borrow page
            raise web.seeother(key + '/borrow') # XXX doesn't work because title is after OL id

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
    
    # Check if hosted at archive.org
    if edition.get('ocaid', False):
        return True
    
    return False

@public
def is_loan_available(edition, type):
    global loanstatus_url
    
    if not loanstatus_url:
        return False
    
    resource_id = edition.get_lending_resource_id(type)
    
    if not resource_id:
        return False
        
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
            return True
        
        if response[0]['returned'] != 'F':
            # Current loan has been returned
            return True
            
    except IOError:
        # status server is down
        # $$$ log
        return False
        
    return False
    
# XXX - currently here for development - put behind user limit and availability checks
@public
def get_loan_link(edition, type):
    global content_server
    
    if not content_server:
        if not config.content_server:
            # $$$ log
            return None
        content_server = ContentServer(config.content_server)
        
    resource_id = edition.get_lending_resource_id(type)
    return content_server.get_loan_link(resource_id)

########## Helper Functions

def get_loans(user):
    return [web.ctx.site.store[result['key']] for result in web.ctx.site.store.query('/type/loan', 'user', user.key)]

########## Classes

class Loan:

    defaultLoanDelta = datetime.timedelta(weeks = 2)
    isoFormat = "%Y-%m-%dT%H:%M:%S.%f"

    def __init__(self, userKey, bookKey, resourceType, expiry = None, loanedAt = None):
        self.userKey = userKey
        self.bookKey = bookKey
        self.resourceType = resourceType
        self.type = '/type/loan'
        
        if loanedAt is not None:
            self.loanedAt = loanedAt
        else:
            self.loanedAt = datetime.datetime.utcnow().isoformat()

        if expiry is not None:
            self.expiry = expiry
        else:
            self.expiry = datetime.datetime.strptime(self.loanedAt, Loan.isoFormat)
        
    def get_key(self):
        return '%s-%s-%s' % (self.userKey, self.bookKey, self.resourceType)
        
    def get_dict(self):
        return { 'user': self.userKey, 'type': '/type/loan',
                 'book': self.bookKey, 'expiry': self.expiry,
                 'loanedAt': self.loanedAt, 'resourceType': self.resourceType }
                 
    def set_dict(self, loanDict):
        self.userKey = loanDict['user']
        self.type = loanDict['type']
        self.bookKey = loanDict['book']
        self.resourceType = loanDict['resourceType']
        self.expiry = loanDict['expiry']
        self.loanedAt = loanDict['loanedAt']
        
    def load(self):
        self.set_dict(web.ctx.site.store[self.get_key()])
        
    def save(self):
        web.ctx.site.store[self.get_key()] = self.get_dict()
        
    def add(self):
        """Record/update the loan"""
        self.save()
        
    def remove(self):
        web.ctx.site.delete(self.get_key())
        
    def create_url(self):
        """Mints a loan URL"""
        # XXX implement
        pieces = ['%s=%s' % (key, value) for (key, value) in self.get_dict().items()]
        return "/?%s" % string.join(pieces, '&')
        
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