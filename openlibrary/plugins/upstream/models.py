
import web
import urllib, urllib2
import simplejson
import re
from lxml import etree
from collections import defaultdict

from infogami import config
from infogami.infobase import client
from infogami.utils.view import safeint

from openlibrary.plugins.search.code import SearchProcessor
from openlibrary.plugins.openlibrary import code as ol_code
from openlibrary.plugins.worksearch.code import works_by_author, sorted_work_editions
from openlibrary.utils.solr import Solr

from utils import get_coverstore_url, MultiDict, parse_toc, parse_datetime, get_edition_config
import account

re_meta_collection = re.compile('<collection>([^<]+)</collection>', re.I)

class Image:
    def __init__(self, category, id):
        self.category = category
        self.id = id
        
    def info(self):
        url = '%s/%s/id/%s.json' % (get_coverstore_url(), self.category, self.id)
        try:
            d = simplejson.loads(urllib2.urlopen(url).read())
            d['created'] = parse_datetime(d['created'])
            if d['author'] == 'None':
                d['author'] = None
            d['author'] = d['author'] and web.ctx.site.get(d['author'])
            
            return web.storage(d)
        except IOError:
            # coverstore is down
            return None
                
    def url(self, size="M"):
        return "%s/%s/id/%s-%s.jpg" % (get_coverstore_url(), self.category, self.id, size.upper())
        
    def __repr__(self):
        return "<image: %s/%d>" % (self.category, self.id)

class Edition(ol_code.Edition):
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
        return self.authors

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
        return [Image('b', c) for c in self.covers if c > 0]
        
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

    def get_ia_collections(self):
        if not self.get('ocaid', None):
            return set()
        ia = self.ocaid
        url = 'http://www.archive.org/download/%s/%s_meta.xml' % (ia, ia)
        matches = (re_meta_collection.search(line) for line in urllib2.urlopen(url))
        return set(m.group(1).lower() for m in matches if m)

    def is_daisy_encrypted(self):
        collections = self.get_ia_collections()
        return 'printdisabled' in collections or 'lendinglibrary' in collections

#      def is_lending_library(self):
#         collections = self.get_ia_collections()
#         return 'lendinglibrary' in collections
        
    def get_lending_resources(self):
        """Returns the loan resource identifiers for books hosted on archive.org"""
        
        # The entries in meta.xml look like this:
        # <external-identifier>
        #     acs:epub:urn:uuid:0df6f344-7ce9-4038-885e-e02db34f2891
        # </external-identifier>
        
        itemid = self.ocaid
        if not itemid:
            self._lending_resources = []
            return self._lending_resources
        url = 'http://www.archive.org/download/%s/%s_meta.xml' % (itemid, itemid)
        # $$$ error handling
        root = etree.parse(urllib2.urlopen(url))
        self._lending_resources = [ elem.text for elem in root.findall('external-identifier') ]
        return self._lending_resources
        
    def get_lending_resource_id(self, type):
        if getattr(self, '_lending_resources', None) is None:
            self.get_lending_resources()

        desired = 'acs:%s:' % type
        for urn in self._lending_resources:
            if urn.startswith(desired):
                return urn[len(desired):]

        return None

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
        names = ['isbn_10', 'isbn_13', 'lccn', 'oclc_numbers', 'ocaid', 'dewey_decimal_class', 'lc_classifications']
        
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
        return self._process_identifiers(get_edition_config().classifications, names, self.classifications)
        
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
        self.physical_dimensions = d and UnitParser(["height", "width", "depth"]).format(d)
        
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
        links1 = [web.storage(url=url, title=title) for url, title in zip(self.uris, self.uri_descriptions)] 
        links2 = list(self.links)
        return links1 + links2
        
    def get_olid(self):
        return self.key.split('/')[-1]
        
class Author(ol_code.Author):
    def get_photos(self):
        return [Image("a", id) for id in self.photos if id > 0]
        
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
        
class Work(ol_code.Work):
    def get_olid(self):
        return self.key.split('/')[-1]

    def get_covers(self):
        if self.covers:
            return [Image("w", id) for id in self.covers if id > 0]
        else:
            return self.get_covers_from_solr()
            
    def get_covers_from_solr(self):
        w = self._solr_data
        if w:
            if 'cover_id' in w:
                return [Image("w", int(w['cover_id']))]
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
        return [a.author for a in self.authors]
    
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


class User(ol_code.User):
    
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

def setup():
    client.register_thing_class('/type/edition', Edition)
    client.register_thing_class('/type/author', Author)
    client.register_thing_class('/type/work', Work)

    client.register_thing_class('/type/subject', Subject)
    client.register_thing_class('/type/place', SubjectPlace)
    client.register_thing_class('/type/person', SubjectPerson)
    client.register_thing_class('/type/user', User)
