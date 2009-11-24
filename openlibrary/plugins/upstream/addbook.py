"""Handlers for adding and editing books."""

import web
from infogami.utils import delegate
from utils import render_template, unflatten
from openlibrary.plugins.openlibrary import code as ol_code

class addbook(delegate.page):
    path = "/books/add"
    
    def GET(self):
        return render_template('books/add1')
        
    def POST(self):
        i = web.input(title='')
        print i
        page = web.ctx.site.new('/books/new', {'key': '/books/new', 'type': '/type/edition', 'title': ''})
        return render_template('books/add2', page)

class addauthor(ol_code.addauthor):
    path = "/authors/add"    

del delegate.pages['/addbook']
# templates still refers to /addauthor.
#del delegate.pages['/addauthor'] 

def strip_values(values):
    """
        >>> strip_values(["a ", "", " b "])
        ["a", "b"]
    """
    return [v.strip() for v in values if v.strip()]

class book_edit(delegate.page):
    path = "(/books/OL\d+M)/edit"
    
    def GET(self, key):
        page = web.ctx.site.get(key)
        if page is None:
            raise web.notfound()
            
        return render_template('books/add2', page)
        
    def POST(self, key):
        book = web.ctx.site.get(key)
        if book is None:
            raise web.notfound()
            
        i = web.input()
        i = self.process_input(i)
        self.save_book(book, i)
        raise web.seeother(key)
        
    def process_input(self, i):
        i = unflatten(i)
        
        book = i.edition
        book.publishers = strip_values(i.get('publishers', '').split(';'))
        book.publish_places = strip_values(i.get('publish_places', '').split(';'))
        
        return i
    
    def save_book(self, book, i):
        book.update(i.edition)
        book._save(comment=i.get('_comment'))
