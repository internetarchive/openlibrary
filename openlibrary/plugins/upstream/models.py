
import web
import urllib, urllib2
import simplejson
import re
from lxml import etree
from collections import defaultdict

from infogami import config
from infogami.infobase import client
from infogami.utils.view import safeint
from infogami.utils import stats

from openlibrary.core import models
from openlibrary.core.models import Image

from openlibrary.plugins.search.code import SearchProcessor
from openlibrary.plugins.worksearch.code import works_by_author, sorted_work_editions
from openlibrary.utils.solr import Solr

from utils import get_coverstore_url, MultiDict, parse_toc, parse_datetime, get_edition_config
import account
import borrow

re_meta_field = re.compile('<(collection|contributor)>([^<]+)</(collection|contributor)>', re.I)

def follow_redirect(doc):
    if doc.type.key == "/type/redirect":
        key = doc.location
        return web.ctx.site.get(key)
    else:
        return doc

class Edition(models.Edition):
    def get_title(self):
        if self['title_prefix']:
            return self['title_prefix'] + ' ' + self['title']
        else:
            return self['title']
            
    def get_title_prefix(self):
        return ''

    # let title be title_prefix + title
    title = property(get_title)
    title_prefix = property(get_title_prefix)
    
    def get_authors(self):
        """Added to provide same interface for work and edition"""
        authors = [follow_redirect(a) for a in self.authors]
        authors = [a for a in authors if a and a.type.key == "/type/author"]
        return authors
        
    def get_next(self):
        """Next edition of work"""
        if len(self.get('works', [])) != 1:
            return
        wkey = self.works[0].get_olid()
        if not wkey:
            return
        editions = sorted_work_editions(wkey)
        try:
            i = editions.index(self.get_olid())
        except ValueError:
            return
        if i + 1 == len(editions):
            return
        return editions[i + 1]

    def get_prev(self):
        """Previous edition of work"""
        if len(self.get('works', [])) != 1:
            return
        wkey = self.works[0].get_olid()
        if not wkey:
            return
        editions = sorted_work_editions(wkey)
        try:
            i = editions.index(self.get_olid())
        except ValueError:
            return
        if i == 0:
            return
        return editions[i - 1]
 
    def get_covers(self):
        return [Image(self._site, 'b', c) for c in self.covers if c > 0]
        
    def get_cover(self):
        covers = self.get_covers()
        return covers and covers[0] or None
        
    def get_cover_url(self, size):
        cover = self.get_cover()
        return cover and cover.url(size)

    def get_identifiers(self):
        """Returns (name, value) pairs of all available identifiers."""
        names = ['isbn_10', 'isbn_13', 'lccn', 'oclc_numbers', 'ocaid']
        return self._process_identifiers(get_edition_config().identifiers, names, self.identifiers)

    def get_ia_meta_fields(self):
        if not self.get('ocaid', None):
            return {}
        ia = self.ocaid
        url = 'http://www.archive.org/download/%s/%s_meta.xml' % (ia, ia)
        reply = { 'collection': set() }
        try:
            stats.begin("archive.org", url=url)
            f = urllib2.urlopen(url)
            stats.end()
        except:
            stats.end()
            return reply
        for line in f:
            m = re_meta_field.search(line)
            if not m:
                continue
            k = m.group(1).lower()
            v = m.group(2)
            if k == 'collection':
                reply[k].add(v.lower())
            else:
                assert k == 'contributor'
                reply[k] = v

        return reply

    def is_daisy_encrypted(self):
        meta_fields = self.get_ia_meta_fields()
        if not meta_fields:
            return
        v = meta_fields['collection']
        return 'printdisabled' in v or 'lendinglibrary' in v

#      def is_lending_library(self):
#         collections = self.get_ia_collections()
#         return 'lendinglibrary' in collections
        
    def get_lending_resources(self):
        """Returns the loan resource identifiers (in meta.xml format for ACS4 resources) for books hosted on archive.org
        
        Returns e.g. ['bookreader:lettertoannewarr00west',
                      'acs:epub:urn:uuid:0df6f344-7ce9-4038-885e-e02db34f2891',
                      'acs:pdf:urn:uuid:7f192e62-13f5-4a62-af48-be4bea67e109']
        """
        
        # The entries in meta.xml look like this:
        # <external-identifier>
        #     acs:epub:urn:uuid:0df6f344-7ce9-4038-885e-e02db34f2891
        # </external-identifier>
        
        itemid = self.ocaid
        if not itemid:
            # Could be e.g. OverDrive
            return []
        
        # Use cached value if available
#         try:
#             return self._lending_resources
#         except AttributeError:
#             pass
#             
#         if not itemid:
#             self._lending_resources = []
#             return self._lending_resources
        
        url = 'http://www.archive.org/download/%s/%s_meta.xml' % (itemid, itemid)
        # $$$ error handling
        stats.begin("archive.org", url=url)
        root = etree.parse(urllib2.urlopen(url))
        stats.end()
        
        self._lending_resources = [ elem.text for elem in root.findall('external-identifier') ]
        
        # Check if available for in-browser lending - marked with 'browserlending' collection
        browserLendingCollections = ['browserlending']
        collections = [ elem.text for elem in root.findall('collection') ]
        for collection in collections:
            if collection in browserLendingCollections:
                self._lending_resources.append('bookreader:%s' % self.ocaid)
                break
        
        return self._lending_resources
        
    def get_lending_resource_id(self, type):
        if type == 'bookreader':
            desired = 'bookreader:'
        else:
            desired = 'acs:%s:' % type
            
        for urn in self.get_lending_resources():
            if urn.startswith(desired):            
                # Got a match                
                # $$$ a little icky - prune the acs:type if present
                if urn.startswith('acs:'):
                    urn = urn[len(desired):]
                    
                return urn

        return None
        
    def get_available_loans(self):
        """Returns [{'resource_id': uuid, 'type': type, 'size': bytes}]
        
        size may be None"""
        
        default_type = 'bookreader'
        
        loans = []
        
        resource_pattern = r'acs:(\w+):(.*)'
        for resource_urn in self.get_lending_resources():
            print 'RESOURCE %s' % resource_urn
            if resource_urn.startswith('acs:'):
                (type, resource_id) = re.match(resource_pattern, resource_urn).groups()
                loans.append( { 'resource_id': resource_id, 'type': type, 'size': None } )
            elif resource_urn.startswith('bookreader'):
                loans.append( { 'resource_id': resource_urn, 'type': 'bookreader', 'size': None } )
            
        
        # Put default type at start of list, then sort by type name
        def loan_key(loan):
            if loan['type'] == default_type:
                return '1-%s' % loan['type']
            else:
                return '2-%s' % loan['type']        
        loans = sorted(loans, key=loan_key)
        
        # Check if we have a possible loan - may not yet be fulfilled in ACS4
        if borrow.get_edition_loans(self):
            # There is a current loan or offer
            return []
            
        # Check if available - book status server
        # We shouldn't be out of sync but we fail safe
        for loan in loans:
            if borrow.is_loaned_out(loan['resource_id']):
                # Only a single loan of an item is allowed
                # XXX log out of sync state
                return []
        
        # XXX get file size
            
        return loans
    
    def update_loan_status(self):
        """Update the loan status"""
        # $$$ search in the store and update
        loans = borrow.get_edition_loans(self)
        for loan in loans:
            borrow.update_loan_status(loan['resource_id'])
            
#         urn_pattern = r'acs:\w+:(.*)'
#         for ia_urn in self.get_lending_resources():
#             if ia_urn.startswith('acs:'):
#                 resource_id = re.match(urn_pattern, ia_urn).group(1)
#             else:
#                 resource_id = ia_urn
# 
#             borrow.update_loan_status(resource_id)

    def _process_identifiers(self, config, names, values):
        id_map = {}
        for id in config:
            id_map[id.name] = id
            id.setdefault("label", id.name)
            id.setdefault("url_format", None)
        
        d = MultiDict()
        
        def process(name, value):
            if value:
                if not isinstance(value, list):
                    value = [value]
                    
                id = id_map.get(name) or web.storage(name=name, label=name, url_format=None)
                for v in value:
                    d[id.name] = web.storage(
                        name=id.name, 
                        label=id.label, 
                        value=v, 
                        url=id.get('url') and id.url.replace('@@@', v))
                
        for name in names:
            process(name, self[name])
            
        for name in values:
            process(name, values[name])
        
        return d
    
    def set_identifiers(self, identifiers):
        """Updates the edition from identifiers specified as (name, value) pairs."""
        names = ('isbn_10', 'isbn_13', 'lccn', 'oclc_numbers', 'ocaid', 
                 'dewey_decimal_class', 'lc_classifications')
        
        d = {}
        for id in identifiers:
            # ignore bad values
            if 'name' not in id or 'value' not in id:
                continue
            name, value = id['name'], id['value']
            d.setdefault(name, []).append(value)
        
        # clear existing value first        
        for name in names:
           self._getdata().pop(name, None)
           
        self.identifiers = {}
            
        for name, value in d.items():
            # ocaid is not a list
            if name == 'ocaid':
                self.ocaid = value[0]
            elif name in names:
                self[name] = value
            else:
                self.identifiers[name] = value

    def get_classifications(self):
        names = ["dewey_decimal_class", "lc_classifications"]
        return self._process_identifiers(get_edition_config().classifications, 
                                         names, 
                                         self.classifications)
        
    def set_classifications(self, classifications):
        names = ["dewey_decimal_class", "lc_classifications"]
        d = defaultdict(list)
        for c in classifications:
            if 'name' not in c or 'value' not in c or not web.re_compile("[a-z0-9_]*").match(c['name']):
                continue
            d[c['name']].append(c['value'])
            
        for name in names:
            self._getdata().pop(name, None)
        self.classifications = {}
        
        for name, value in d.items():
            if name in names:
                self[name] = value
            else:
                self.classifications[name] = value
            
    def get_weight(self):
        """returns weight as a storage object with value and units fields."""
        w = self.weight
        return w and UnitParser(["value"]).parse(w)
        
    def set_weight(self, w):
        self.weight = w and UnitParser(["value"]).format(w)
        
    def get_physical_dimensions(self):
        d = self.physical_dimensions
        return d and UnitParser(["height", "width", "depth"]).parse(d)
    
    def set_physical_dimensions(self, d):
        # don't overwrite physical dimensions if nothing was passed in - there
        # may be dimensions in the database that don't conform to the d x d x d format
        if d:
            self.physical_dimensions = UnitParser(["height", "width", "depth"]).format(d)
        
    def get_toc_text(self):
        def format_row(r):
            return "*" * r.level + " " + " | ".join([r.label, r.title, r.pagenum])
            
        return "\n".join(format_row(r) for r in self.get_table_of_contents())
        
    def get_table_of_contents(self):
        def row(r):
            if isinstance(r, basestring):
                level = 0
                label = ""
                title = r
                pagenum = ""
            else:
                level = safeint(r.get('level', '0'), 0)
                label = r.get('label', '')
                title = r.get('title', '')
                pagenum = r.get('pagenum', '')
                
            r = web.storage(level=level, label=label, title=title, pagenum=pagenum)
            return r
            
        d = [row(r) for r in self.table_of_contents]
        return [row for row in d if any(row.values())]

    def set_toc_text(self, text):
        self.table_of_contents = parse_toc(text)
        
    def get_links(self):
        links1 = [web.storage(url=url, title=title) 
                  for url, title in zip(self.uris, self.uri_descriptions)] 
        links2 = list(self.links)
        return links1 + links2
        
    def get_olid(self):
        return self.key.split('/')[-1]
    
    @property
    def wp_citation_fields(self):
        """
        Builds a wikipedia citation as defined by http://en.wikipedia.org/wiki/Template:Cite#Citing_books
        """
        result = {
            "title": self.works[0].title.replace("[", "&#91").replace("]", "&#93"),
            "publication-date": self.get('publish_date'),
            "url": "http://openlibrary.org%s" % self.url()
        }

        if self.title != self.works[0].title:
            result['edition'] = self.title

        if self.get('isbn_10'):
            result['id'] = self['isbn_10'][0]
            result['isbn'] = self['isbn_13'][0] if self.get('isbn_13') else self['isbn_10'][0]

        if self.get('oclc_numbers'):
            result['oclc'] = self.oclc_numbers[0]

        if self.works[0].get('first_publish_year'):
            result['origyear'] = self.works[0]['first_publish_year']

        if self.get('publishers'):
            result['publisher'] = self['publishers'][0]

        if self.get('publish_places'):
            result['publication-place'] = self['publish_places'][0]

        authors = [ar.author for ar in self.works[0].authors]
        if len(authors) == 1:
            result['author'] = authors[0].name
        else:
            for i, a in enumerate(authors):
                result['author%s' % (i + 1)] = a.name 
        return result
        
class Author(models.Author):
    def get_photos(self):
        return [Image(self._site, "a", id) for id in self.photos if id > 0]
        
    def get_photo(self):
        photos = self.get_photos()
        return photos and photos[0] or None
        
    def get_photo_url(self, size):
        photo = self.get_photo()
        return photo and photo.url(size)
    
    def get_olid(self):
        return self.key.split('/')[-1]

    def get_books(self):
        i = web.input(sort='editions', page=1)
        try:
            page = int(i.page)
        except ValueError:
            page = 1
        return works_by_author(self.get_olid(), sort=i.sort, page=page, rows=100)

re_year = re.compile(r'(\d{4})$')

def get_works_solr():
    base_url = "http://%s/solr/works" % config.plugin_worksearch.get('solr')
    return Solr(base_url)
        
class Work(models.Work):
    def get_olid(self):
        return self.key.split('/')[-1]

    def get_covers(self):
        if self.covers:
            return [Image(self._site, "w", id) for id in self.covers if id > 0]
        else:
            return self.get_covers_from_solr()
            
    def get_covers_from_solr(self):
        w = self._solr_data
        if w:
            if 'cover_id' in w:
                return [Image(self._site, "w", int(w['cover_id']))]
            elif 'cover_edition_key' in w:
                cover_edition = web.ctx.site.get("/books/" + w['cover_edition_key'])
                cover = cover_edition and cover_edition.get_cover()
                if cover:
                    return [cover]
        return []
        
    def _get_solr_data(self):
        key = self.get_olid()
        fields = ["cover_edition_key", "cover_id", "edition_key", "first_publish_year"]
        
        solr = get_works_solr()
        d = solr.select({"key": key}, fields=fields)
        if d.num_found > 0:
            w = d.docs[0]
        else:
            w = None
                
        # Replace _solr_data property with the attribute
        self.__dict__['_solr_data'] = w
        return w
        
    _solr_data = property(_get_solr_data)
    
    def get_cover(self):
        covers = self.get_covers()
        return covers and covers[0] or None
    
    def get_cover_url(self, size):
        cover = self.get_cover()
        return cover and cover.url(size)
        
    def get_authors(self):
        authors =  [a.author for a in self.authors]
        authors = [follow_redirect(a) for a in authors]
        authors = [a for a in authors if a and a.type.key == "/type/author"]
        return authors
    
    def get_subjects(self):
        """Return subject strings."""
        subjects = self.subjects
        
        def flip(name):
            if name.count(",") == 1:
                a, b = name.split(",")
                return b.strip() + " " + a.strip()
            return name
                
        if subjects and not isinstance(subjects[0], basestring):
            subjects = [flip(s.name) for s in subjects]
        return subjects
        
    def get_sorted_editions(self):
        """Return a list of works sorted by publish date"""
        w = self._solr_data
        editions = w and w.get('edition_key')
        
        if editions:
            return web.ctx.site.get_many(["/books/" + olid for olid in editions])
        else:
            return []

    first_publish_year = property(lambda self: self._solr_data.get("first_publish_year"))
        
    def get_edition_covers(self):
        editions = web.ctx.site.get_many(web.ctx.site.things({"type": "/type/edition", "works": self.key, "limit": 1000}))
        exisiting = set(int(c.id) for c in self.get_covers())
        covers = [e.get_cover() for e in editions]
        return [c for c in covers if c and int(c.id) not in exisiting]

class Subject(client.Thing):
    def _get_solr_result(self):
        if not self._solr_result:
            name = self.name or ""
            q = {'subjects': name, "facets": True}
            self._solr_result = SearchProcessor().search(q)
        return self._solr_result
        
    def get_related_subjects(self):
        # dummy subjects
        return [web.storage(name='France', key='/subjects/places/France'), web.storage(name='Travel', key='/subjects/Travel')]
        
    def get_covers(self, offset=0, limit=20):
        editions = self.get_editions(offset, limit)
        olids = [e['key'].split('/')[-1] for e in editions]
        
        try:
            url = '%s/b/query?cmd=ids&olid=%s' % (get_coverstore_url(), ",".join(olids))
            data = urllib2.urlopen(url).read()
            cover_ids = simplejson.loads(data)
        except IOError, e:
            print >> web.debug, 'ERROR in getting cover_ids', str(e) 
            cover_ids = {}
            
        def make_cover(edition):
            edition = dict(edition)
            edition.pop('type', None)
            edition.pop('subjects', None)
            edition.pop('languages', None)
            
            olid = edition['key'].split('/')[-1]
            if olid in cover_ids:
                edition['cover_id'] = cover_ids[olid]
            
            return edition
            
        return [make_cover(e) for e in editions]
    
    def get_edition_count(self):
        d = self._get_solr_result()
        return d['matches']
        
    def get_editions(self, offset, limit=20):
        if self._solr_result and offset+limit < len(self._solr_result):
            result = self._solr_result[offset:offset+limit]
        else:
            name = self.name or ""
            result = SearchProcessor().search({"subjects": name, 'offset': offset, 'limit': limit})
        return result['docs']
        
    def get_author_count(self):
        d = self._get_solr_result()
        return len(d['facets']['authors'])
        
    def get_authors(self):
        d = self._get_solr_result()
        return [web.storage(name=a, key='/authors/OL1A', count=count) for a, count in d['facets']['authors']]
    
    def get_publishers(self):
        d = self._get_solr_result()
        return [web.storage(name=p, count=count) for p, count in d['facets']['publishers']]


class SubjectPlace(Subject):
    pass
    

class SubjectPerson(Subject):
    pass


class User(models.User):
    
    def get_name(self):
        return self.displayname or self.key.split('/')[-1]
    name = property(get_name)
    
    def get_edit_history(self, limit=10, offset=0):
        return web.ctx.site.versions({"author": self.key, "limit": limit, "offset": offset})
        
    def get_email(self):
        if web.ctx.path.startswith("/admin"):
            return account.get_user_email(self.key)
            
    def get_creation_info(self):
        if web.ctx.path.startswith("/admin"):
            d = web.ctx.site.versions({'key': self.key, "sort": "-created", "limit": 1})[0]
            return web.storage({"ip": d.ip, "member_since": d.created})
            
    def get_edit_count(self):
        if web.ctx.path.startswith("/admin"):
            return web.ctx.site._request('/count_edits_by_user', data={"key": self.key})
        else:
            return 0
            
    def get_loan_count(self):
        return len(borrow.get_loans(self))
        
    def update_loan_status(self):
        """Update the status of this user's loans."""
        loans = borrow.get_loans(self)
        for resource_id in [loan['resource_id'] for loan in loans]:
            borrow.update_loan_status(resource_id)
            
class UnitParser:
    """Parsers values like dimentions and weight.

        >>> p = UnitParser(["height", "width", "depth"])
        >>> p.parse("9 x 3 x 2 inches")
        <Storage {'units': 'inches', 'width': '3', 'depth': '2', 'height': '9'}>
        >>> p.format({"height": "9", "width": 3, "depth": 2, "units": "inches"})
        '9 x 3 x 2 inches'
    """
    def __init__(self, fields):
        self.fields = fields

    def format(self, d):
        return " x ".join(str(d.get(k, '')) for k in self.fields) + ' ' + d.get('units', '')

    def parse(self, s):
        """Parse the string and return storage object with specified fields and units."""
        pattern = "^" + " *x *".join("([0-9.]*)" for f in self.fields) + " *(.*)$"
        rx = web.re_compile(pattern)
        m = rx.match(s)
        return m and web.storage(zip(self.fields + ["units"], m.groups()))

class Changeset(client.Changeset):
    def can_undo(self):
        return False
        
    def _undo(self):
        """Undo this transaction."""
        docs = {}
        
        def get_doc(key, revision):
            if revision == 0:
                return {
                    "key": key,
                    "type": {"key": "/type/delete"}
                }
            else:
                return web.ctx.site.get(key, revision).dict()
        
        docs = [get_doc(c['key'], c['revision']-1) for c in self.changes]
        data = {
            "parent_changeset": self.id
        }
        comment = 'undo ' + self.comment
        return web.ctx.site.save_many(docs, action="undo", data=data, comment=comment)
            
    def get_undo_changeset(self):
        """Returns the changeset that undone this transaction if one exists, None otherwise.
        """
        try:
            return self._undo_changeset
        except AttributeError:
            pass
        
        changesets = web.ctx.site.recentchanges({
            "kind": "undo", 
            "data": {
                "parent_changeset": self.id
            }
        })
        # return the first undo changeset
        self._undo_changeset = changesets and changesets[-1] or None
        return self._undo_changeset

class MergeAuthors(Changeset):
    def can_undo(self):
        return self.get_undo_changeset() is None
        
    def get_master(self):
        master = self.data.get("master")
        return master and web.ctx.site.get(master, lazy=True)
        
    def get_duplicates(self):
        duplicates = self.data.get("duplicates")
        changes = dict((c['key'], c['revision']) for c in self.changes)
        
        return duplicates and [web.ctx.site.get(key, revision=changes[key]-1, lazy=True) for key in duplicates if key in changes]
        
class Undo(Changeset):
    def can_undo(self):
        return False
    
    def get_undo_of(self):
        undo_of = self.data['undo_of']
        return web.ctx.site.get_change(undo_of)
        
    def get_parent_changeset(self):
        parent = self.data['parent_changeset']
        return web.ctx.site.get_change(parent)
        
class AddBookChangeset(Changeset):
    def get_work(self):
        book = self.get_edition()
        return (book and book.works and book.works[0]) or None
    
    def get_edition(self):
        for doc in self.get_changes():
            if doc.key.startswith("/books/"):
                return doc
        
    def get_author(self):
        for doc in self.get_changes():
            if doc.key.startswith("/authors/"):
                return doc
    
def setup():
    models.register_models()
    
    client.register_thing_class('/type/edition', Edition)
    client.register_thing_class('/type/author', Author)
    client.register_thing_class('/type/work', Work)

    client.register_thing_class('/type/subject', Subject)
    client.register_thing_class('/type/place', SubjectPlace)
    client.register_thing_class('/type/person', SubjectPerson)
    client.register_thing_class('/type/user', User)

    client.register_changeset_class(None, Changeset) # set the default class
    client.register_changeset_class('merge-authors', MergeAuthors)
    client.register_changeset_class('undo', Undo)

    client.register_changeset_class('add-book', AddBookChangeset)
