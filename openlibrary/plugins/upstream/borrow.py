"""Handlers for borrowing books"""

import web

from infogami import config
from infogami.utils import delegate

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