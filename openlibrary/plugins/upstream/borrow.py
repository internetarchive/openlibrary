"""Handlers for borrowing books"""

import web

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import public

import utils
from utils import render_template

# Handler for /books/{bookid}/{title}/borrow
class borrow(delegate.page):
	path = "(/books/OL\d+M)/borrow"
	
	def GET(self, key):
		book = web.ctx.site.get(key)
		
		if not book:
			raise web.notfound()
			
		return render_template("borrow", book)
		
class do_borrow(delegate.page):
    """Actually borrow the book, via POST"""
    path = "(/books/OL\d+M)/_doborrow"
    
    def POST(self, key):
        i = web.input()
        
        user = web.ctx.site.get_user()
        
        everythingChecksOut = True # XXX
        if everythingChecksOut:
            # XXX get loan URL and loan id
            loanid = 'loan1'
            expiry = '2010'
            resourceType = 'epub'
            loan_url = '/?loanid=%s&bookid=%s&expiry=%s&debug=true' % (loanid, key, expiry)
            add_user_loan(user, key, resourceType, expiry)
            raise web.seeother(loan_url)
        else:
            # Send to the borrow page
            raise web.seeother(key + '/borrow') # XXX doesn't work because title is after OL id
            
@public
def get_own_loans():
    return get_user_loans(web.ctx.site.get_user())
    

def key_for_loan(user, bookId, resourceType):
    return '%s-%s-%s' % (user, bookId, resourceType)
    
def obj_for_loan(user, bookId, resourceType, expiry):
    return { 'type': '/type/loan', 'user': user.key,
             'bookId': bookId, 'expiry': expiry }
             
def get_user_loans(user):
    return [web.ctx.site.store[result['key']] for result in web.ctx.site.store.query('/type/loan', 'user', user.key)]
    
def add_user_loan(user, bookId, resourceType, expiry):
    web.ctx.site.store[key_for_loan(user, bookId, resourceType)] = obj_for_loan(user, bookId, resourceType, expiry)
    
def remove_user_loan(user, bookId, resourceType):
    return web.ctx.site.store.delete(key_for_loan(user, bookId, resourceType))
