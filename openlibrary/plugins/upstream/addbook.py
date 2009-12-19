"""Handlers for adding and editing books."""

import web
import urllib, urllib2

from infogami import config
from infogami.core import code as core
from infogami.utils import delegate

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
    return web.storage((k, trim_value(v)) for k, v in doc.items() if k[:1] not in "_{")
    
class SaveBookHelper:
    """Helper to save edition and work using the form data coming from edition edit and work edit pages.
    
    This does the required trimming and processing of input data before saving.
    """
    def __init__(self, work, edition):
        self.work = work
        self.edition = edition
    
    def save(self, formdata):
        """Update work and edition documents according to the specified formdata."""
        work_data, edition_data = self.process_input(formdata)
        
        if work_data:
            self.work.update(work_data)
            self.work._save()
            
        if self.edition and edition_data:
            self.edition.update(edition_data)
            self.edition._save()
    
    def process_input(self, i):
        i = unflatten(i)
        
        if 'edition' in i:
            edition = self.process_edition(i.edition)
        else:
            edition = None
            
        if 'work' in i:
            work = self.process_work(i.work)
        else:
            work = None
            
        return work, edition
    
    def process_edition(self, edition):
        """Process input data for edition."""
        edition.publishers = edition.get('publishers', '').split(';')
        edition.publish_places = edition.get('publish_places', '').split(';')
        
        edition = trim_doc(edition)

        if edition.get('dimensions') and edition.dimensions.keys() == ['units']:
            edition.dimensions = None

        if edition.get('editionweight') and edition.editionweight.keys() == ['unit']:
            edition.editionweight = None
            
        return edition
        
    def process_work(self, work):
        """Process input data for work."""
        work.subjects = work.get('subjects', '').split(',')
        work.subject_places = work.get('subject_places', '').split(',')
        work.subject_times = work.get('subject_times', '').split(',')
        work.subject_people = work.get('subject_people', '').split(',')
        
        work = trim_doc(work)
        
        return work
        

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
        edition = web.ctx.site.get(key)
        if edition is None:
            raise web.notfound()
        
        if edition.works:
            work = edition.works[0]
        else:
            work_key = web.ctx.site.new_key("/type/work")
            work = web.ctx.site.new(work_key, {
                "key": work_key, 
                "type": {'key': '/type/work'},
                "title": edition.title, 
                "authors": [{"author": a, "type": {"key": "/type/author_role"}} for a in edition.authors]
            })
            work._save()
            edition.works = [work]
            
        helper = SaveBookHelper(work, edition)
        helper.save(web.input())
        raise web.seeother(edition.url())

class work_edit(delegate.page):
    path = "(/works/OL\d+W)/edit"
    
    def GET(self, key):
        work = web.ctx.site.get(key)
        if work is None:
            raise web.notfound()
        return render_template('books/edit', work)
        
    def POST(self, key):
        work = web.ctx.site.get(key)
        if work is None:
            raise web.notfound()
            
        helper = SaveBookHelper(work, None)
        helper.save(web.input())
        raise web.seeother(work.url())

        
class author_edit(delegate.page):
    path = "(/authors/OL\d+A)/edit"
    
    def GET(self, key):
        author = web.ctx.site.get(key)
        if author is None:
            raise web.notfound()
        return render_template("type/author/edit", author)
        
    def POST(self, key):
        author = web.ctx.site.get(key)
        if author is None:
            raise web.notfound()
            
        i = web.input(_comment=None)
        
        formdata = self.process_input(i)
        if formdata:
            author.update(formdata)
            author._save(comment=i._comment)
            raise web.seeother(key)
        else:
            raise web.badrequest()
    
    def process_input(self, i):
        i = unflatten(i)
        if 'author' in i:
            author = trim_doc(i.author)
            author.alternate_names = [name.strip() for name in author.get('alternate_names', '').split(';')]
            return author
            
class edit(core.edit):
    """Overwrite ?m=edit behaviour for author, book and work pages"""
    def GET(self, key):
        page = web.ctx.site.get(key)

        # first token is always empty string. second token is what we want.
        if key.split("/")[1] in ["authors", "books", "works"]:
            raise web.seeother(page.url(suffix="/edit"))
        else:
            return core.edit.GET(self, key)
        
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
