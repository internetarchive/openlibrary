"""Handlers for adding and editing books."""

import web
import urllib, urllib2
import simplejson

from infogami import config
from infogami.core import code as core
from infogami.utils import delegate
from infogami.utils.view import safeint

from openlibrary.plugins.openlibrary import code as ol_code
from openlibrary.plugins.openlibrary.processors import urlsafe

import utils
from utils import render_template

from account import as_admin

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
        comment = formdata.pop('_comment', '')
        work_data, edition_data = self.process_input(formdata)
        
        self.process_new_fields(formdata)
        
        if work_data:
            self.work.update(work_data)
            self.work._save(comment=comment)
            
        if self.edition and edition_data:
            identifiers = edition_data.pop('identifiers', [])
            self.edition.set_identifiers(identifiers)
            
            classifications = edition_data.pop('classifications', [])
            self.edition.set_classifications(classifications)
            
            self.edition.set_physical_dimensions(edition_data.pop('physical_dimensions', None))
            self.edition.set_weight(edition_data.pop('weight', None))
            self.edition.set_toc_text(edition_data.pop('table_of_contents', ''))
            
            if edition_data.pop('translation', None) != 'yes':
                edition_data.translation_of = None
                edition_data.translated_from = None
            
            self.edition.update(edition_data)
            self.edition._save(comment=comment)
            
    def process_new_fields(self, formdata):
        def f(name):
            val = formdata.get(name)
            return val and simplejson.loads(val)
            
        new_roles = f('select-role-json')
        new_ids = f('select-id-json')
        new_classifications = f('select-classification-json')
        
        if new_roles or new_ids or new_classifications:
            edition_config = web.ctx.site.get('/config/edition')
            
            #TODO: take care of duplicate names
            
            if new_roles:
                edition_config.roles += [d.get('value') or '' for d in new_roles]
                
            if new_ids:
                edition_config.identifiers += [{
                        "name": d.get('value') or '', 
                        "label": d.get('label') or '', 
                        "website": d.get("website") or '', 
                        "notes": d.get("notes") or ''} 
                    for d in new_ids]
                
            if new_classifications:
                edition_config.classifications += [{
                        "name": d.get('value') or '', 
                        "label": d.get('label') or '', 
                        "website": d.get("website") or '', 
                        "notes": d.get("notes") or ''}
                    for d in new_classifications]
                    
            as_admin(edition_config._save)("add new fields")
    
    def process_input(self, i):
        i = utils.unflatten(i)
        
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
        edition.distributors = edition.get('distributors', '').split(';')
        
        edition = trim_doc(edition)

        if edition.get('physical_dimensions') and edition.physical_dimensions.keys() == ['units']:
            edition.physical_dimensions = None

        if edition.get('weight') and edition.weight.keys() == ['units']:
            edition.weight = None
            
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
        i = utils.unflatten(i)
        if 'author' in i:
            author = trim_doc(i.author)
            alternate_names = author.get('alternate_names', None) or ''
            author.alternate_names = [name.strip() for name in alternate_names.split(';')]
            return author
            
class edit(core.edit):
    """Overwrite ?m=edit behaviour for author, book and work pages"""
    def GET(self, key):
        page = web.ctx.site.get(key)
        
        if page is None:
            raise web.seeother(key)

        # first token is always empty string. second token is what we want.
        if key.split("/")[1] in ["authors", "books", "works"]:
            raise web.seeother(page.url(suffix="/edit"))
        else:
            return core.edit.GET(self, key)
        
def to_json(d):
    web.header('Content-Type', 'application/json')    
    return delegate.RawText(simplejson.dumps(d))

class languages_autocomplete(delegate.page):
    path = "/languages/_autocomplete"
    
    def GET(self):
        i = web.input(q="", limit=5)
        i.limit = safeint(i.limit, 5)
        
        languages = [lang for lang in utils.get_languages() if lang.name.lower().startswith(i.q.lower())]
        return to_json(languages[:i.limit])
        
class authors_autocomplete(delegate.page):
    path = "/authors/_autocomplete"
    
    def GET(self):
        i = web.input(q="", limit=5)
        i.limit = safeint(i.limit, 5)
        
        d = []
        if "mark twain".startswith(i.q):
            d.append(dict(name="Mark Twain", key="/authors/OL18319A", subjects=["Fiction", "Tom Sawyer"], works=["a"]))
            
        if "margaret mahy".startswith(i.q):
            d.append(dict(name="Margaret Mahy", key="/authors/OL4398065A", subjects=["Fiction"], works=["b"]))

        return to_json(d)
                
def setup():
    """Do required setup."""
    pass
