"""Handlers for adding and editing books."""

import web
import urllib, urllib2
import simplejson

from infogami import config
from infogami.core import code as core
from infogami.core.db import ValidationException
from infogami.utils import delegate
from infogami.utils.view import safeint, add_flash_message
from infogami.infobase.client import ClientException

from openlibrary.plugins.openlibrary import code as ol_code
from openlibrary.plugins.openlibrary.processors import urlsafe
from openlibrary.utils.solr import Solr

import utils
from utils import render_template

from account import as_admin

def get_works_solr():
    base_url = "http://%s/solr/works" % config.plugin_worksearch.get('solr')
    return Solr(base_url)
    
def make_work(doc):
    w = web.storage(doc)
    w.key = "/works/" + w.key
    
    def make_author(key, name):
        key = "/authors/" + key
        return web.ctx.site.new(key, {
            "key": key,
            "type": {"key": "/type/author"},
            "name": name
        })
    
    w.authors = [make_author(key, name) for key, name in zip(doc['author_key'], doc['author_name'])]
    w.cover_url="/images/icons/avatar_book-sm.png"
    
    w.setdefault('ia', [])
    w.setdefault('first_publish_year', None)
    return w
    
def new_doc(type, **data):
    key = web.ctx.site.new_key(type)
    data['key'] = key
    data['type'] = {"key": type}
    return web.ctx.site.new(key, data)

class addbook(delegate.page):
    path = "/books/add"
    
    def GET(self):
        i = web.input(work=None)
        work = i.work and web.ctx.site.get(i.work)        
        return render_template('books/add', work)
        
    def POST(self):
        i = web.input(title="", author="", author_key="")
        match = self.find_matches(i)
        
        if match is None:
            # no match
            return self.no_match(i)

        elif isinstance(match, list):
            # multiple matches
            return render_template("books/check", i.title, i.author, result.docs)

        elif match.key.startswith('/books'):
            # work match and edition match
            return self.work_edition_match()

        elif match.key.startswith('/works'):
            # work match but not edition
            work = match
            return self.work_match(work, i)
                        
    def find_matches(self, i):
        """Tries to find an edition or a work or multiple works that match the given input data.
        
        Case#1: No match. None is returned.
        Case#2: Work match but not editon. Work is returned.
        Case#3: Work match and edition match. Edition is returned
        Case#4: Multiple work match. List of works is returned. 
        """
        work = i.get('work') and web.ctx.site.get(i.work)
        if work:
            # check for edition
            return work
        
        solr = get_works_solr()
        result = solr.select({'title': i.title, 'author_key': i.author_key}, doc_wrapper=make_work)
        
        if i.author_key == "__new__":
            a = new_doc("/type/author", name=i.author)
            a._save("New author")
            i.author_key = a.key
            # since new author is created it must be a new record
            return None
        
        if result.num_found == 0:
            return None
        elif result.num_found == 1:
            return work
        else:
            return result.docs
    
    def work_match(self, work, i):
        edition = self._make_edition(work, i)            
        edition._save("New edition")        
        raise web.seeother(edition.url("/edit"))
        
    def _make_edition(self, work, i):
        edition = new_doc("/type/edition", 
            works=[{"key": work.key}],
            title=i.title,
            publishers=[i.publisher],
            publish_date=i.publish_date,
        )
        if i.get("id_name") and i.get("id_value"):
            edition.set_identifiers([dict(name=i.id_name, value=i.id_value)])
        return edition
        
    def work_edition_match(self):
        return "Not yet implemented"
        
    def multiple_matches(self):
        return "Not yet implemented"
        
    def no_match(self, i):
        # TODO: Handle add-new-author
        work = new_doc("/type/work",
            title=i.title,
            authors=[{"author": {"key": i.author_key}}]
        )
        work._save("New work")
        
        edition = self._make_edition(work, i)
        edition._save("New edition")
        raise web.seeother(edition.url("/edit"))

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

        user = web.ctx.site.get_user()
        delete = user and user.is_admin() and formdata.pop('_delete', '')
        
        work_data, edition_data = self.process_input(formdata)
        
        self.process_new_fields(formdata)
        
        if delete:
            if self.edition:
                self.delete(self.edition.key, comment=comment)
            
            if self.work and self.work.edition_count == 0:
                self.delete(self.work.key, comment=comment)
            return
            
        for author in work_data.get("authors") or []:
            if author['author']['key'] == "__new__":
                a = self.new_author(formdata['author'])
                a._save("New author")
                author['author']['key'] = a.key
            
        if work_data and not delete:
            if self.work is None:
                self.work = self.new_work(self.edition)
                self.edition.works = [{'key': self.work.key}]
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
    
    def new_work(self, edition):
        work_key = web.ctx.site.new_key("/type/work")
        work = web.ctx.site.new(work_key, {
            "key": work_key, 
            "type": {'key': '/type/work'},
        })
        return work
        
    def new_author(self, name):
        key =  web.ctx.site.new_key("/type/author")
        return web.ctx.site.new(key, {
            "key": key,
            "type": {"key": "/type/author"},
            "name": name
        })

    def delete(self, key, comment=""):
        doc = web.ctx.site.new(key, {
            "key": key,
            "type": {"key": "/type/delete"}
        })
        doc._save(comment=comment)
        
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
            
        for k in ['roles', 'identifiers', 'classifications']:
            edition[k] = edition.get(k) or []
            
        return edition
        
    def process_work(self, work):
        """Process input data for work."""
        work.subjects = work.get('subjects', '').split(',')
        work.subject_places = work.get('subject_places', '').split(',')
        work.subject_times = work.get('subject_times', '').split(',')
        work.subject_people = work.get('subject_people', '').split(',')
        
        for k in ['excerpts', 'links']:
            work[k] = work.get(k) or []
        
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
        work = work or web.ctx.site.new('', {'key': '', 'type': {'key': '/type/work'}, 'title': edition.title})
        return render_template('books/edit', work, edition)
        
    def POST(self, key):
        edition = web.ctx.site.get(key)
        if edition is None:
            raise web.notfound()
        if edition.works:
            work = edition.works[0]
        else:
            work = None
            
        try:    
            helper = SaveBookHelper(work, edition)
            helper.save(web.input())
            raise web.seeother(edition.url())
        except (ClientException, ValidationException), e:
            raise
            add_flash_message('error', str(e))
            return self.GET(key)

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

        try:
            helper = SaveBookHelper(work, None)
            helper.save(web.input())
            raise web.seeother(work.url())
        except (ClientException, ValidationException), e:
            add_flash_message('error', str(e))
            return self.GET(key)
        
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
        try:
            if not formdata:
                raise web.badrequest()
            elif "_save" in i:
                author.update(formdata)
                author._save(comment=i._comment)
                raise web.seeother(key)
            elif "_delete" in i:
                author = web.ctx.site.new(key, {"key": key, "type": {"key": "/type/delete"}})
                author._save(comment=i._comment)
                raise web.seeother(key)
        except (ClientException, ValidationException), e:
            add_flash_message('error', str(e))
            author.update(formdata)
            author['comment_'] = i._comment
            return render_template("type/author/edit", author)
    
    def process_input(self, i):
        i = utils.unflatten(i)
        if 'author' in i:
            author = trim_doc(i.author)
            alternate_names = author.get('alternate_names', None) or ''
            author.alternate_names = [name.strip() for name in alternate_names.replace("\n", ";").split(';')]
            author.links = author.get('links') or []
            return author
            
class edit(core.edit):
    """Overwrite ?m=edit behaviour for author, book and work pages"""
    def GET(self, key):
        page = web.ctx.site.get(key)
        
        if web.re_compile('/(authors|books|works)/OL.*').match(key):
            if page is None:
                raise web.seeother(key)
            else:
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
        
        # temporary implementation until author solr is ready
        data = web.ctx.site.things(
                {"type": "/type/author", "name~": i.q.title() + "*", "sort": "name", "name": None, "limit": i.limit}, 
                details=True)
        for d in data:
            d.subjects = []
            d.works = [w.title for w in 
                        web.ctx.site.things(
                            {"type": "/type/work", "authors": {"author": {"key": d.key}}, "title": None, "limit": 2}, 
                            details=True)]
        
        return to_json(data)
                
def setup():
    """Do required setup."""
    pass
