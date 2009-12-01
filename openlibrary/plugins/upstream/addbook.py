"""Handlers for adding and editing books."""

import web
import urllib, urllib2
from infogami.utils import delegate
from infogami import config

from openlibrary.plugins.openlibrary import code as ol_code

from utils import render_template, unflatten


class addbook(delegate.page):
    path = "/books/add"
    
    def GET(self):
        return render_template('books/add')
        
    def POST(self):
        i = web.input(title='')
        work = web.ctx.site.new('/works/new', {'key': '/works/new', 'type': {'key': '/type/work'}, 'title': ''})
        edition = web.ctx.site.new('/books/new', {'key': '/books/new', 'type': {'key': '/type/edition'}, 'title': ''})
        return render_template('books/edit', work, edition)


class addauthor(ol_code.addauthor):
    path = "/authors/add"    

del delegate.pages['/addbook']
# templates still refers to /addauthor.
#del delegate.pages['/addauthor'] 

def trim_value(value):
    """Trim strings, lists and dictionaries to remove empty/None values.
    
        >>> trim_value("hello ")
        'hello'
        >>> trim_value("")
        >>> trim_value([1, 2, ""])
        [1, 2]
        >>> trim_value({'x': 'a', 'y': ''})
        {'x': 'a'}
        >>> trim_value({'x': [""]})
        None
    """
    if isinstance(value, basestring):
        value = value.strip()
        return value or None        
    elif isinstance(value, list):
        value = [v2 for v in value
                    for v2 in [trim_value(v)]
                    if v2 is not None]
        return value or None
    elif isinstance(value, dict):
        value = dict((k, v2) for k, v in value.items()
                             for v2 in [trim_value(v)]
                             if v2 is not None)
        return value or None
    else:
        return value
        
def trim_doc(doc):
    """Replace empty values in the document with Nones.
    """
    return web.storage((k, trim_value(v)) for k, v in doc.items())

class book_edit(delegate.page):
    path = "(/books/OL\d+M)/edit"
    
    def GET(self, key):
        edition = web.ctx.site.get(key)
        if edition is None:
            raise web.notfound()
            
        work = edition.works and edition.works[0]
        # HACK: create dummy work when work is not available to make edit form work
        work = work or web.ctx.site.new('/works/new', {'key': '/works/new', 'type': {'key': '/type/work'}, 'title': edition.title})
        return render_template('books/edit', work, edition)
        
    def POST(self, key):
        book = web.ctx.site.get(key)
        if book is None:
            raise web.notfound()
            
        i = web.input()
        i = self.process_input(i)
        self.save_book(book, i)
        raise web.seeother(key)
        
    def process_input(self, i):
        # input has keys like "edition--title" for edition values and keys like "work--title" for work values.
        # The unflatten function converts them into a dictionary.
        i = unflatten(i)
        
        book = i.edition
        book.publishers = book.get('publishers', '').split(';')
        book.publish_places = book.get('publish_places', '').split(';')
        i.edition = self.trim_edition(book)
        
        return i
        
    def trim_edition(self, book):
        book = trim_doc(book)
        
        if 'dimensions' in book and book.dimensions.keys() == ['units']:
            book.dimensions = None

        if 'bookweight' in book and book.bookweight.keys() == ['unit']:
            book.bookweight = None
        return book
            
    def save_book(self, book, i):
        book.update(i.edition)
        book._save(comment=i.get('_comment'))

class work_edit(delegate.page):
    path = "(/works/OL\d+W)/edit"
    
    def GET(self, key):
        work = web.ctx.site.get(key)
        if work is None:
            raise web.notfound()
        return render_template('books/edit', work)

class uploadcover(delegate.page):
    def POST(self):
        user = web.ctx.site.get_user()
        i = web.input(file={}, url=None, key="")
        
        olid = i.key and i.key.split("/")[-1]
        
        if i.file is not None:
            data = i.file.value
        else:
            data = None
            
        if i.url and i.url.strip() == "http://":
            i.url = ""

        upload_url = config.get('coverstore_url', 'http://covers.openlibrary.org') + '/b/upload2'
        params = dict(author=user and user.key, data=data, source_url=i.url, olid=olid, ip=web.ctx.ip)
        try:
            response = urllib2.urlopen(upload_url, urllib.urlencode(params))
            out = response.read()
        except urllib2.HTTPError, e:
            out = e.read()
            
        web.header("Content-Type", "text/javascript")
        return delegate.RawText(out)
        
        
def setup():
    """Do required setup."""
    pass