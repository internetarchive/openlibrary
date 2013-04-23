import httplib, re, sys
from openlibrary.catalog.utils.query import query_iter, withKey, has_cover, set_query_host
#from openlibrary.catalog.marc.marc_subject import get_work_subjects, four_types
from lxml.etree import tostring, Element, SubElement
from pprint import pprint
import urllib2
from urllib2 import URLError, HTTPError
import simplejson as json
import time
import web
from openlibrary import config
from unicodedata import normalize
from collections import defaultdict
from openlibrary.utils.isbn import opposite_isbn
from openlibrary.core import helpers as h
import logging
import datetime

logger = logging.getLogger("openlibrary.solr")

re_lang_key = re.compile(r'^/(?:l|languages)/([a-z]{3})$')
re_author_key = re.compile(r'^/(?:a|authors)/(OL\d+A)')
#re_edition_key = re.compile(r'^/(?:b|books)/(OL\d+M)$')
re_edition_key = re.compile(r"/books/([^/]+)")

solr_host = {}

def urlopen(url, data=None):
    version = "%s.%s.%s" % sys.version_info[:3]
    user_agent = 'Mozilla/5.0 (openlibrary; %s) Python/%s' % (__file__, version)
    headers = {
        'User-Agent': user_agent
    }
    req = urllib2.Request(url, data, headers)
    return urllib2.urlopen(req)

def get_solr(index):
    global solr_host

    if not config.runtime_config:
        config.load('openlibrary.yml')

    if not solr_host:
        solr_host = {
            'works': config.runtime_config['plugin_worksearch']['solr'],
            'authors': config.runtime_config['plugin_worksearch']['author_solr'],
            'subjects': config.runtime_config['plugin_worksearch']['subject_solr'],
            'editions': config.runtime_config['plugin_worksearch']['edition_solr'],
        }
    return solr_host[index]
    
def load_config():
    if not config.runtime_config:
        config.load('openlibrary.yml')

def is_single_core():
    """Returns True if we are using new single core solr setup that maintains
    all type of documents in a single core."""
    return config.runtime_config.get("single_core_solr", False)

def is_borrowed(edition_key):
    """Returns True of the given edition is borrowed.
    """
    key = "/books/" + edition_key
    
    load_config()
    infobase_server = config.runtime_config.get("infobase_server")
    if infobase_server is None:
        print "infobase_server not defined in the config. Unabled to find borrowed status."
        return False
            
    url = "http://%s/openlibrary.org/_store/ebooks/books/%s" % (infobase_server, edition_key)
    
    try:
        d = json.loads(urlopen(url).read())
        print edition_key, d
    except HTTPError, e:
        # Return False if that store entry is not found 
        if e.getcode() == 404:
            return False
        # Ignore errors for now
        return False
    return d.get("borrowed", "false") == "true"

re_collection = re.compile(r'<(collection|boxid)>(.*)</\1>', re.I)

def get_ia_collection_and_box_id(ia):
    if len(ia) == 1:
        return

    def get_list(d, key):
        value = d.get(key, [])
        if not isinstance(value, list):
            value = [value]
        return value

    matches = {'boxid': set(), 'collection': set() }
    url = "http://archive.org/metadata/%s/metadata" % ia
    logger.info("loading metadata from %s", url)
    for attempt in range(5):
        try:
            d = json.loads(urlopen(url).read()).get('result', {})
            matches['boxid'] = set(get_list(d, 'boxid'))
            matches['collection'] = set(get_list(d, 'collection'))
        except URLError:
            print "retry", attempt, url
            time.sleep(5)
    return matches

class AuthorRedirect (Exception):
    pass

re_bad_char = re.compile('[\x01\x0b\x1a-\x1e]')
re_year = re.compile(r'(\d{4})$')
re_iso_date = re.compile(r'^(\d{4})-\d\d-\d\d$')
def strip_bad_char(s):
    if not isinstance(s, basestring):
        return s
    return re_bad_char.sub('', s)

def add_field(doc, name, value):
    field = Element("field", name=name)
    try:
        field.text = normalize('NFC', unicode(strip_bad_char(value)))
    except:
        print `value`
        raise
    doc.append(field)

def add_field_list(doc, name, field_list):
    for value in field_list:
        add_field(doc, name, value)

to_drop = set(''';/?:@&=+$,<>#%"{}|\\^[]`\n\r''')

def str_to_key(s):
    return ''.join(c if c != ' ' else '_' for c in s.lower() if c not in to_drop)

re_not_az = re.compile('[^a-zA-Z]')
def is_sine_nomine(pub):
    return re_not_az.sub('', pub).lower() == 'sn'

def pick_cover(w, editions):
    w_cover = w['covers'][0] if w.get('covers', []) else None
    first_with_cover = None
    for e in editions:
        if 'covers' not in e:
            continue
        if w_cover and e['covers'][0] == w_cover:
            return e['key']
        if not first_with_cover:
            first_with_cover = e['key']
        for l in e.get('languages', []):
            if 'eng' in l:
                return e['key']
    return first_with_cover

def get_work_subjects(w):
    wkey = w['key']
    assert w['type']['key'] == '/type/work'

    subjects = {}
    field_map = {
        'subjects': 'subject',
        'subject_places': 'place',
        'subject_times': 'time',
        'subject_people': 'person',
    }

    for db_field, solr_field in field_map.iteritems():
        if not w.get(db_field, None):
            continue
        cur = subjects.setdefault(solr_field, {})
        for v in w[db_field]:
            try:
                if isinstance(v, dict):
                    if 'value' not in v:
                        continue
                    v = v['value']
                cur[v] = cur.get(v, 0) + 1
            except:
                print 'v:', v
                raise

    return subjects

def four_types(i):
    want = set(['subject', 'time', 'place', 'person'])
    ret = dict((k, i[k]) for k in want if k in i)
    for j in (j for j in i.keys() if j not in want):
        for k, v in i[j].items():
            if 'subject' in ret:
                ret['subject'][k] = ret['subject'].get(k, 0) + v
            else:
                ret['subject'] = {k: v}
    return ret

def datetimestr_to_int(datestr):
    if isinstance(datestr, dict):
        datestr = datestr['value']

    if datestr:
        try:
            t = h.parse_datetime(datestr)
        except (TypeError, ValueError):
            t = datetime.datetime.utcnow()
    else:
        t = datetime.datetime.utcnow()

    return int(time.mktime(t.timetuple()))

class SolrProcessor:
    """Processes data to into a form suitable for adding to works solr.
    """
    def __init__(self, obj_cache=None, resolve_redirects=False):
        if obj_cache is None:
            obj_cache = {}
        self.obj_cache = obj_cache
        self.resolve_redirects = resolve_redirects
        
    def process(data):
        """Builds solr document from data. 

        The data is expected to have all the required information to build the doc.
        If some information is not found, it is considered to be missing. The
        expected format is:

            {
                "work": {...},
                "editions": [{...}, {...}],
            }
        
        This functions returns a dictionary containing the following fields:

            title
            subtitle
            has_fulltext
            alternative_title
            alternative_subtitle
            edition_count
            edition_key
            cover_edition_key
            covers_i
            by_statement
            

        """
        # Not yet implemented
        pass

    def process_edition(self, e):
        """Processes an edition and returns a new dictionary with fields required for solr indexing.
        """
        d = {}
        pub_year = self.get_pub_year(e)
        if pub_year:
            d['pub_year'] = pub_year

        # Assuming the ia collections info is added to the edition as "_ia"
        if "_ia" in e:
            ia = e["ia"]
        else:
            # TODO
            pass

        ia = e.get("ocaid") or e.get("ia_loaded_id") or None
        if isinstance(ia, list):
            ia = ia[0]
            

    def get_ia_id(self, edition):
        """Returns ia identifier from an edition dict.
        """
        if "ocaid" in e:
            return e["ocaid"]
        elif e.get("ia_loaded_id"):
            return self.ensure_string(e['ia_loaded_id'][0])

    def ensure_string(self, value):
        if isinstance(value, basestring):
            return value


    def sanitize_edition(self, e):
        """Takes an edition and corrects bad data.

        This will make sure:

        * ia_loaded_id - is a list of strings
        * ia_box_id - is a list of strings
        """
        e["ia_loaded_id"] = self.ensure_list(e.get("ia_loaded_id"), basestring)
        e["ia_box_id"] = self.ensure_list(e.get("ia_box_id"), basestring)


    def ensure_list(self, value, elem_type):
        """Ensures that value is a list of elem_type elements.

            >>> ensure_list([1, "foo", 2], int)
            [1, 2]
            >>> ensure_list("foo", int)
            []
            >>> ensure_list(None, int)
            []
            >>> ensure_list(1, int)
            [1]
        """
        if not value:
            return []
        elif isinstance(value, list):
            return [v for v in value if isinstance(v, elem_type)]
        elif isinstance(value, elem_type):
            # value is supposed to be of type (listof elem_type) but it is of type elem_type by mistake.
            return [value]
        else:
            return []

    def process_editions(self, w, identifiers):
        editions = []
        for e in w['editions']:
            pub_year = self.get_pub_year(e)
            if pub_year:
                e['pub_year'] = pub_year
            ia = None
            if 'ocaid' in e:
                ia = e['ocaid']
            elif 'ia_loaded_id' in e:
                loaded = e['ia_loaded_id']
                ia = loaded if isinstance(loaded, basestring) else loaded[0]

            # If the _ia_meta field is already set in the edition, use it instead of querying archive.org.
            # This is useful to when doing complete reindexing of solr.
            if ia and '_ia_meta' in e:
                ia_meta_fields = e['_ia_meta']
            elif ia:
                ia_meta_fields = get_ia_collection_and_box_id(ia)
            else:
                ia_meta_fields = None

            if ia_meta_fields:
                collection = ia_meta_fields['collection']
                if 'ia_box_id' in e and isinstance(e['ia_box_id'], basestring):
                    e['ia_box_id'] = [e['ia_box_id']]
                if ia_meta_fields.get('boxid'):
                    box_id = list(ia_meta_fields['boxid'])[0]
                    e.setdefault('ia_box_id', [])
                    if box_id.lower() not in [x.lower() for x in e['ia_box_id']]:
                        e['ia_box_id'].append(box_id)
                #print 'collection:', collection
                e['ia_collection'] = collection
                e['public_scan'] = ('lendinglibrary' not in collection) and ('printdisabled' not in collection)
                print "e.public_scan", e["public_scan"]
            overdrive_id = e.get('identifiers', {}).get('overdrive', None)
            if overdrive_id:
                #print 'overdrive:', overdrive_id
                e['overdrive'] = overdrive_id
            if 'identifiers' in e:
                for k, id_list in e['identifiers'].iteritems():
                    k_orig = k
                    k = k.replace('.', '_').replace(',', '_').replace('(', '').replace(')', '').replace(':', '_').replace('/', '').replace('#', '').lower()
                    m = re_solr_field.match(k)
                    if not m:
                        print (k_orig, k)
                    assert m
                    for v in id_list:
                        v = v.strip()
                        if v not in identifiers[k]:
                            identifiers[k].append(v)
            editions.append(e)

        editions.sort(key=lambda e: e.get('pub_year', None))
        return editions

    def get_author(self, a):
        """Returns the author dict from author entry in the work.

            get_author({"author": {"key": "/authors/OL1A"}})
        """
        if 'author' not in a: # OL Web UI bug
            return # http://openlibrary.org/works/OL15365167W.yml?m=edit&v=1

        author = a['author']

        if 'type' in author:
            # means it is already the whole object. 
            # It'll be like this when doing re-indexing of solr.
            return author
        
        key = a['author']['key']
        m = re_author_key.match(key)
        if not m:
            print 'invalid author key:', key
            return
        return withKey(key)
    
    def extract_authors(self, w):
        authors = [self.get_author(a) for a in w.get("authors", [])]
        work_authors = [a['key'] for a in authors]
        author_keys = [a['key'].split("/")[-1] for a in authors]

        if any(a['type']['key'] == '/type/redirect' for a in authors):
            if self.resolve_redirects:
                def resolve(a):
                    if a['type']['key'] == '/type/redirect':
                        a = withKey(a['location'])
                    return a
                authors = [resolve(a) for a in authors]
            else:
                print
                for a in authors:
                    print 'author:', a
                print w['key']
                print
                raise AuthorRedirect
        assert all(a['type']['key'] == '/type/author' for a in authors)
        return authors

    def get_pub_year(self, e):
        pub_date = e.get('publish_date', None)
        if pub_date:
            m = re_iso_date.match(pub_date)
            if m:
                return m.group(1)
            m = re_year.search(pub_date)
            if m:
                return m.group(1)
                
    def get_subject_counts(self, w, editions, has_fulltext):
        try:
            subjects = four_types(get_work_subjects(w))
        except:
            print 'bad work: ', w['key']
            raise

        field_map = {
            'subjects': 'subject',
            'subject_places': 'place',
            'subject_times': 'time',
            'subject_people': 'person',
        }

        for db_field, solr_field in field_map.iteritems():
            if not w.get(db_field, None):
                continue
            cur = subjects.setdefault(solr_field, {})
            for v in w[db_field]:
                try:
                    if isinstance(v, dict):
                        if 'value' not in v:
                            continue
                        v = v['value']
                    cur[v] = cur.get(v, 0) + 1
                except:
                    print 'v:', v
                    raise

        if any(e.get('ocaid', None) for e in editions):
            subjects.setdefault('subject', {})
            subjects['subject']['Accessible book'] = subjects['subject'].get('Accessible book', 0) + 1
            if not has_fulltext:
                subjects['subject']['Protected DAISY'] = subjects['subject'].get('Protected DAISY', 0) + 1
            #print w['key'], subjects['subject']
        return subjects
        
    def build_data(self, w, editions, subjects, has_fulltext):
        d = {}
        def add(name, value):
            if value is not None:
                d[name] = value
                
        def add_list(name, values):
            d[name] = list(values)
        
        # when using common solr core for all types of documents, 
        # use the full key and add type to the doc.
        if is_single_core():
            add('key', w['key'])
            add('type', 'work')
            add('seed', BaseDocBuilder().compute_seeds(w, editions))
        else:    
            add('key', w['key'][7:]) # strip /works/

        add('title', w.get('title'))
        add('subtitle', w.get('subtitle'))
        add('has_fulltext', has_fulltext)

        add_list("alternative_title", self.get_alternate_titles(w, editions))
        add_list('alternative_subtitle', self.get_alternate_subtitles(w, editions))

        add('edition_count', len(editions))
        add_list("edition_key", [re_edition_key.match(e['key']).group(1) for e in editions])
        add_list("by_statement", set(e["by_statement"] for e in editions if "by_statement" in e))
        
        k = 'publish_date'
        pub_dates = set(e[k] for e in editions if e.get(k))
        add_list(k, pub_dates)
        pub_years = set(m.group(1) for m in (re_year.search(date) for date in pub_dates) if m)
        if pub_years:
            add_list('publish_year', pub_years)
            add('first_publish_year', min(int(y) for y in pub_years))
            
        field_map = [
            ('lccn', 'lccn'),
            ('publish_places', 'publish_place'),
            ('oclc_numbers', 'oclc'),
            ('contributions', 'contributor'),
        ]
        for db_key, solr_key in field_map:
            values = set(v for e in editions 
                           if db_key in e
                           for v in e[db_key])
            add_list(solr_key, values)
            
        add_list("isbn", self.get_isbns(editions))
        add("last_modified_i", self.get_last_modified(w, editions))

        self.add_ebook_info(d, editions)
        return d
        
        
    def get_alternate_titles(self, w, editions):
        result = set()
        for e in editions:
            result.add(e.get('title'))
            result.update(e.get('work_titles', []))
            result.update(e.get('other_titles', []))
            
        # Remove original title and None.
        # None would've got in if any of the editions has no title.
        result.discard(None)
        result.discard(w.get('title'))
        return result

    def get_alternate_subtitles(self, w, editions):
        subtitle = w.get('subtitle')
        return set(e['subtitle'] for e in editions if e.get('subtitle') and e['subtitle'] != subtitle)
        
    def get_isbns(self, editions):
        isbns = set()

        isbns.update(v.replace("_", "").strip() for e in editions for v in e.get("isbn_10", []))
        isbns.update(v.replace("_", "").strip() for e in editions for v in e.get("isbn_13", []))
        
        # Get the isbn13 when isbn10 is present and vice-versa.
        alt_isbns = [opposite_isbn(v) for v in isbns]
        isbns.update(v for v in alt_isbns if v is not None)
        
        return isbns        

    def get_last_modified(self, work, editions):
        return max(datetimestr_to_int(doc.get('last_modified')) for doc in [work] + editions)
        
    def add_ebook_info(self, doc, editions):
        def add(name, value):
            if value is not None:
                doc[name] = value
                
        def add_list(name, values):
            doc[name] = list(values)

        pub_goog = set() # google
        pub_nongoog = set()
        nonpub_goog = set()
        nonpub_nongoog = set()

        public_scan = False
        all_collection = set()
        all_overdrive = set()
        lending_edition = None
        in_library_edition = None
        printdisabled = set()
        for e in editions:
            if 'overdrive' in e:
                all_overdrive.update(e['overdrive'])
            if 'ocaid' not in e:
                continue
            if not lending_edition and 'lendinglibrary' in e.get('ia_collection', []):
                lending_edition = re_edition_key.match(e['key']).group(1)
            if not in_library_edition and 'inlibrary' in e.get('ia_collection', []):
                in_library_edition = re_edition_key.match(e['key']).group(1)
            if 'printdisabled' in e.get('ia_collection', []):
                printdisabled.add(re_edition_key.match(e['key']).group(1))
            all_collection.update(e.get('ia_collection', []))
            assert isinstance(e['ocaid'], basestring)
            i = e['ocaid'].strip()
            print i, e.get("public_scan")
            if e.get('public_scan'):
                public_scan = True
                if i.endswith('goog'):
                    pub_goog.add(i)
                else:
                    pub_nongoog.add(i)
            else:
                if i.endswith('goog'):
                    nonpub_goog.add(i)
                else:
                    nonpub_nongoog.add(i)
        ia_list = list(pub_nongoog) + list(pub_goog) + list(nonpub_nongoog) + list(nonpub_goog)
        add("ebook_count_i", len(ia_list))

        has_fulltext = any(e.get('ocaid', None) for e in editions)

        add_list('ia', ia_list)
        if has_fulltext:
            add('public_scan_b', public_scan)
        if all_collection:
            add('ia_collection_s', ';'.join(all_collection))
        if all_overdrive:
            add('overdrive_s', ';'.join(all_overdrive))
        if lending_edition:
            add('lending_edition_s', lending_edition)
        elif in_library_edition:
            add('lending_edition_s', in_library_edition)
        if printdisabled:
            add('printdisabled_s', ';'.join(list(printdisabled)))
        

re_solr_field = re.compile('^[-\w]+$', re.U)

def build_doc(w, obj_cache=None, resolve_redirects=False):
    if obj_cache is None:
        obj_cache = {}
    d = build_data(w, obj_cache=obj_cache, resolve_redirects=resolve_redirects)
    return dict2element(d)
    
def dict2element(d):
    doc = Element("doc")
    for k, v in d.items():
        if isinstance(v, (list, set)):
            add_field_list(doc, k, v)
        else:
            add_field(doc, k, v)
    return doc

def build_data(w, obj_cache=None, resolve_redirects=False):
    if obj_cache:
        obj_cache = {}

    wkey = w['key']
    assert w['type']['key'] == '/type/work'
    title = w.get('title', None)
    if not title:
        return
        
    p = SolrProcessor(obj_cache, resolve_redirects)
    get_pub_year = p.get_pub_year

    # Load stuff if not already provided
    if 'editions' not in w:
        q = { 'type':'/type/edition', 'works': wkey, '*': None }
        w['editions'] = list(query_iter(q))
        #print 'editions:', [e['key'] for e in w['editions']]

    identifiers = defaultdict(list)
    editions = p.process_editions(w, identifiers)
    authors = p.extract_authors(w)

    has_fulltext = any(e.get('ocaid', None) for e in editions)
    
    subjects = p.get_subject_counts(w, editions, has_fulltext)
            
    def add_field(doc, name, value):
        doc[name] = value

    def add_field_list(doc, name, field_list):
        doc[name] = list(field_list)
    
    doc = p.build_data(w, editions, subjects, has_fulltext)
    

    cover_edition = pick_cover(w, editions)
    if cover_edition:
        add_field(doc, 'cover_edition_key', re_edition_key.match(cover_edition).group(1))
    if w.get('covers'):
        cover = w['covers'][0]
        assert isinstance(cover, int)
        add_field(doc, 'cover_i', cover)

    k = 'first_sentence'
    fs = set( e[k]['value'] if isinstance(e[k], dict) else e[k] for e in editions if e.get(k, None))
    add_field_list(doc, k, fs)

    publishers = set()
    for e in editions:
        publishers.update('Sine nomine' if is_sine_nomine(i) else i for i in e.get('publishers', []))
    add_field_list(doc, 'publisher', publishers)
#    add_field_list(doc, 'publisher_facet', publishers)

    lang = set()
    ia_loaded_id = set()
    ia_box_id = set()

    last_modified_i = datetimestr_to_int(w.get('last_modified'))

    for e in editions:
        for l in e.get('languages', []):
            m = re_lang_key.match(l['key'] if isinstance(l, dict) else l)
            lang.add(m.group(1))
        if e.get('ia_loaded_id'):
            if isinstance(e['ia_loaded_id'], basestring):
                ia_loaded_id.add(e['ia_loaded_id'])
            else:
                try:
                    assert isinstance(e['ia_loaded_id'], list) and isinstance(e['ia_loaded_id'][0], basestring)
                except AssertionError:
                    print e.get('ia')
                    print e['ia_loaded_id']
                    raise
                ia_loaded_id.update(e['ia_loaded_id'])
        if e.get('ia_box_id'):
            if isinstance(e['ia_box_id'], basestring):
                ia_box_id.add(e['ia_box_id'])
            else:
                try:
                    assert isinstance(e['ia_box_id'], list) and isinstance(e['ia_box_id'][0], basestring)
                except AssertionError:
                    print e['key']
                    raise
                ia_box_id.update(e['ia_box_id'])
    if lang:
        add_field_list(doc, 'language', lang)

        
    #if lending_edition or in_library_edition:
    #    add_field(doc, "borrowed_b", is_borrowed(lending_edition or in_library_edition))

    author_keys = [re_author_key.match(a['key']).group(1) for a in authors]
    author_names = [a.get('name', '') for a in authors]
    add_field_list(doc, 'author_key', author_keys)
    add_field_list(doc, 'author_name', author_names)

    alt_names = set()
    for a in authors:
        if 'alternate_names' in a:
            alt_names.update(a['alternate_names'])

    add_field_list(doc, 'author_alternative_name', alt_names)
    add_field_list(doc, 'author_facet', (' '.join(v) for v in zip(author_keys, author_names)))
    #if subjects:
    #    add_field(doc, 'fiction', subjects['fiction'])

    for k in 'person', 'place', 'subject', 'time':
        if k not in subjects:
            continue
        add_field_list(doc, k, subjects[k].keys())
        add_field_list(doc, k + '_facet', subjects[k].keys())
        subject_keys = [str_to_key(s) for s in subjects[k].keys()]
        add_field_list(doc, k + '_key', subject_keys)

    for k in sorted(identifiers.keys()):
        add_field_list(doc, 'id_' + k, identifiers[k])

    if ia_loaded_id:
        add_field_list(doc, 'ia_loaded_id', ia_loaded_id)

    if ia_box_id:
        add_field_list(doc, 'ia_box_id', ia_box_id)
        
    return doc
    
def solr_update(requests, debug=False, index='works'):
    # As of now, only works are added to single core solr. 
    # Need to work on supporting other things later
    if is_single_core() and index not in ['works', 'authors', 'editions']:
        return

    h1 = httplib.HTTPConnection(get_solr(index))

    if is_single_core():
        url = 'http://%s/solr/update' % get_solr(index)
    else:
        url = 'http://%s/solr/%s/update' % (get_solr(index), index)
    print url
    h1.connect()
    for r in requests:
        if debug:
            print 'request:', `r[:65]` + '...' if len(r) > 65 else `r`
        assert isinstance(r, basestring)
        h1.request('POST', url, r, { 'Content-type': 'text/xml;charset=utf-8'})
        response = h1.getresponse()
        response_body = response.read()
        if response.reason != 'OK':
            print response.reason
            print response_body
        assert response.reason == 'OK'
        if debug:
            print response.reason
#            print response_body
#            print response.getheaders()
    h1.close()

def withKey_cached(key, obj_cache={}):
    if key not in obj_cache:
        obj_cache[key] = withKey(key)
    return obj_cache[key]

def listify(f):
    """Decorator to transform a generator function into a function
    returning list of values.
    """
    def g(*a, **kw):
        return list(f(*a, **kw))
    return g

class BaseDocBuilder:
    re_subject = re.compile("[, _]+")

    @listify
    def compute_seeds(self, work, editions, authors=None):
        """Computes seeds from given work, editions and authors.

        If authors is not supplied, it is infered from the work.
        """

        for e in editions:
            yield e['key']

        if work:
            yield work['key']
            for s in self.get_subject_seeds(work):
                yield s

            if authors is None:
                authors = [a['author'] for a in work.get("authors", []) 
                           if 'author' in a and 'key' in a['author']]

        if authors:
            for a in authors:
                yield a['key']

    def get_subject_seeds(self, work):
        """Yields all subject seeds from the work.
        """
        return (
            self._prepare_subject_keys("/subjects/", work.get("subjects")) +
            self._prepare_subject_keys("/subjects/person:", work.get("subject_people")) +
            self._prepare_subject_keys("/subjects/place:", work.get("subject_places")) +
            self._prepare_subject_keys("/subjects/time:", work.get("subject_times")))

    def _prepare_subject_keys(self, prefix, subject_names):
        subject_names = subject_names or []
        return [self.get_subject_key(prefix, s) for s in subject_names]

    def get_subject_key(self, prefix, subject):
        if isinstance(subject, basestring):
            key = prefix + self.re_subject.sub("_", subject.lower()).strip("_")
            return key

class EditionBuilder(BaseDocBuilder):
    """Helper to edition solr data.
    """
    def __init__(self, edition, work, authors):
        self.edition = edition
        self.work = work
        self.authors = authors

    def build(self):
        return dict(self._build())

    def _build(self):
        yield 'key', self.edition['key']
        yield 'type', 'edition'
        yield 'title', self.edition.get('title') or ''
        yield 'seed', self.compute_seeds(self.work, [self.edition])

        has_fulltext = bool(self.edition.get("ocaid"))
        yield 'has_fulltext', has_fulltext

        last_modified = datetimestr_to_int(self.edition.get('last_modified'))
        yield 'last_modified_i', last_modified

class SolrRequestSet:
    def __init__(self):
        self.deletes = []
        self.docs = []

    def delete(self, key):
        self.deletes.append(key)

    def add(self, doc):
        self.docs.append(doc)

    def get_requests(self):
        return list(self._get_requests())

    def _get_requests(self):
        requests = []
        requests += [make_delete_query(self.deletes)]
        requests += [self._add_request(doc) for doc in self.docs]
        return requests

    def _add_request(self, doc):
        """Constructs add request using doc dict.
        """
        node = dict2element(doc)
        root = Element("add")
        root.append(node)
        return tostring(root).encode('utf-8')

def update_edition(e):
    if not is_single_core():
        return []

    ekey = e['key']
    logger.info("updating edition %s", ekey)

    wkey = e.get('works') and e['works'][0]['key']
    w = wkey and withKey(wkey)
    authors = []

    request_set = SolrRequestSet()
    request_set.delete(ekey)

    q = {'type': '/type/redirect', 'location': ekey}
    redirect_keys = [r['key'] for r in query_iter(q)]
    for k in redirect_keys:
        request_set.delete(k)

    doc = EditionBuilder(e, w, authors).build()
    request_set.add(doc)
    return request_set.get_requests()

def update_work(w, obj_cache=None, debug=False, resolve_redirects=False):
    if obj_cache is None:
        obj_cache = {}

    wkey = w['key']
    #assert wkey.startswith('/works')
    #assert '/' not in wkey[7:]
    deletes = []
    requests = []

    q = {'type': '/type/redirect', 'location': wkey}
    redirect_keys = [r['key'][7:] for r in query_iter(q)]

    deletes += redirect_keys
    deletes += [wkey[7:]] # strip /works/ from /works/OL1234W

    # handle edition records as well
    # When an edition is not belonged to a work, create a fake work and index it.
    if w['type']['key'] == '/type/edition' and w.get('title'):
        edition = w
        w = {
            # Use key as /works/OL1M. 
            # In case of single-core-solr, we are using full path as key. So it is required
            # to be unique across all types of documents.
            # The website takes care of redirecting /works/OL1M to /books/OL1M.
            'key': edition['key'].replace("/books/", "/works/"),
            'type': {'key': '/type/work'},
            'title': edition['title'],
            'editions': [edition]
        }
        # Hack to add subjects when indexing /books/ia:xxx
        if edition.get("subjects"):
            w['subjects'] = edition['subjects']

    if w['type']['key'] == '/type/work' and w.get('title'):
        try:
            d = build_data(w, obj_cache=obj_cache, resolve_redirects=resolve_redirects)
            doc = dict2element(d)
        except:
            logger.error("failed to update work %s", w['key'], exc_info=True)
        else:
            if d is not None:
                # Delete all ia:foobar keys
                # 
                if d.get('ia'):
                    deletes += ["ia:" + iaid for iaid in d['ia']]

                # In single core solr, we use full path as key, not just the last part
                if is_single_core():
                    deletes = ["/works/" + k for k in deletes]

                requests.append(make_delete_query(deletes))

                add = Element("add")
                add.append(doc)
                add_xml = tostring(add).encode('utf-8')
                requests.append(add_xml)

    return requests

def make_delete_query(keys):
    # Escape ":" in the keys.
    # ":" is a special charater and keys like "ia:foo00bar" will
    # fail if ":" is not escaped
    keys = [key.replace(":", r"\:") for key in keys]
    queries = ['<query>key:%s</query>' % key for key in keys]
    return '<delete>%s</delete>' % ''.join(queries)

def update_author(akey, a=None, handle_redirects=True):
    # http://ia331507.us.archive.org:8984/solr/works/select?indent=on&q=author_key:OL22098A&facet=true&rows=1&sort=edition_count%20desc&fl=title&facet.field=subject_facet&facet.mincount=1
    if akey == '/authors/':
        return
    m = re_author_key.match(akey)
    if not m:
        print 'bad key:', akey
    assert m
    author_id = m.group(1)
    if not a:
        a = withKey(akey)
    if a['type']['key'] in ('/type/redirect', '/type/delete') or not a.get('name', None):
        return ['<delete><query>key:%s</query></delete>' % author_id] 
    try:
        assert a['type']['key'] == '/type/author'
    except AssertionError:
        print a['type']['key']
        raise

    facet_fields = ['subject', 'time', 'person', 'place']

    if is_single_core():
        base_url = 'http://' + get_solr('works') + '/solr/select'
    else:
        base_url = 'http://' + get_solr('works') + '/solr/works/select'

    url = base_url + '?wt=json&json.nl=arrarr&q=author_key:%s&sort=edition_count+desc&rows=1&fl=title,subtitle&facet=true&facet.mincount=1' % author_id
    url += ''.join('&facet.field=%s_facet' % f for f in facet_fields)

    logger.info("urlopen %s", url)

    reply = json.load(urlopen(url))
    work_count = reply['response']['numFound']
    docs = reply['response'].get('docs', [])
    top_work = None
    if docs:
        top_work = docs[0]['title']
        if docs[0].get('subtitle', None):
            top_work += ': ' + docs[0]['subtitle']
    all_subjects = []
    for f in facet_fields:
        for s, num in reply['facet_counts']['facet_fields'][f + '_facet']:
            all_subjects.append((num, s))
    all_subjects.sort(reverse=True)
    top_subjects = [s for num, s in all_subjects[:10]]

    add = Element("add")
    doc = SubElement(add, "doc")
    
    if is_single_core():
        add_field(doc, 'key', "/authors/" + author_id)
        add_field(doc, 'type', "author")
    else:
        add_field(doc, 'key', author_id)

    if a.get('name', None):
        add_field(doc, 'name', a['name'])
    for f in 'birth_date', 'death_date', 'date':
        if a.get(f, None):
            add_field(doc, f, a[f])
    if top_work:
        add_field(doc, 'top_work', top_work)
    add_field(doc, 'work_count', work_count)
    add_field_list(doc, 'top_subjects', top_subjects)

    requests = []
    if handle_redirects:
        q = {'type': '/type/redirect', 'location': akey}
        try:
            redirects = ''.join('<id>%s</id>' % re_author_key.match(r['key']).group(1) for r in query_iter(q))
        except AttributeError:
            print 'redirects:', [r['key'] for r in query_iter(q)]
            raise
        if redirects:
            requests.append('<delete>' + redirects + '</delete>')

    requests.append(tostring(add).encode('utf-8'))
    return requests

def commit_and_optimize(debug=False):
    requests = ['<commit />', '<optimize />']
    solr_update(requests, debug)

def update_keys(keys, commit=True):
    logger.info("BEGIN update_keys")
    wkeys = set()

    # Get works for all the editions
    ekeys = set(k for k in keys if k.startswith("/books/"))
    for k in ekeys:
        logger.info("processing edition %s", k)
        edition = withKey(k)
        if not edition:
            logger.warn("No edition found for key %r. Ignoring...", k)
            continue

        if edition.get("works"):
            wkeys.add(edition["works"][0]['key'])
        else:
            # index the edition as it does not belong to any work
            wkeys.add(k)
        
    # Add work keys
    wkeys.update(k for k in keys if k.startswith("/works/"))
    
    # update works
    requests = []
    for k in wkeys:
        logger.info("updating %s", k)
        try:
            w = withKey(k)
            requests += update_work(w, debug=True)
        except:
            logger.error("Failed to update work %s", k, exc_info=True)

    if requests:    
        if commit:
            requests += ['<commit />']
        solr_update(requests, debug=True)

    # update editions
    requests = []
    for k in ekeys:
        try:
            e = withKey(k)
            requests += update_edition(e)
        except:
            logger.error("Failed to update edition %s", k, exc_info=True)
        if requests:
            if commit:
                requests += ['<commit/>']
            solr_update(requests, index="editions", debug=True)


    
    # update authors
    requests = []
    akeys = set(k for k in keys if k.startswith("/authors/"))
    for k in akeys:
        logger.info("updating %s", k)
        try:
            requests += update_author(k)
        except:
            logger.error("Failed to update author %s", k, exc_info=True)
    if requests:  
        if commit:
            requests += ['<commit />']
        solr_update(requests, index="authors", debug=True)
    logger.info("END update_keys")

def parse_options(args=None):
    from optparse import OptionParser
    parser = OptionParser(args)
    parser.add_option("-s", "--server", dest="server", default="http://openlibrary.org/", help="URL of the openlibrary website (default: %default)")
    parser.add_option("-c", "--config", dest="config", default="openlibrary.yml", help="Open Library config file")
    parser.add_option("--nocommit", dest="nocommit", action="store_true", default=False, help="Don't commit to solr")
    parser.add_option("--monkeypatch", dest="monkeypatch", action="store_true", default=False, help="Monkeypatch query functions to access DB directly")

    options, args = parser.parse_args()
    return options, args

def new_query_iter(q, limit=500, offset=0):
    """Alternative implementation of query_iter, that talks to the
    database directly instead of accessing the website API.

    This is set to `query_iter` when this script is called with
    --monkeypatch option.
    """
    q['limit'] = limit
    q['offset'] = offset
    site = web.ctx.site

    while True:
        keys = site.things(q)
        docs = keys and site.get_many(keys, raw=True) 
        for doc in docs:
            yield doc

        # We haven't got as many we have requested. No point making one more request
        if len(keys) < limit:
            break
        q['offset'] += limit

def new_withKey(key):
    """Alternative implementation of withKey, that talks to the database
    directly instead of using the website API.

    This is set to `withKey` when this script is called with --monkeypatch
    option.
    """
    return web.ctx.site._request('/get', data={'key': key})

def monkeypatch(config_file):
    """Monkeypatch query functions to avoid hitting openlibrary.org.
    """
    def load_infogami(config_file):
        import web
        import infogami
        from infogami import config
        from infogami.utils import delegate

        config.plugin_path += ['openlibrary.plugins']
        config.site = "openlibrary.org"
        
        infogami.load_config(config_file)
        setup_infobase_config(config_file)

        infogami._setup()
        delegate.fakeload()
        
    def setup_infobase_config(config_file):
        """Reads the infoabse config file and assign it to config.infobase.
        The config_file is used as base to resolve relative path, if specified in the config.
        """
        from infogami import config
        import os
        import yaml

        if config.get("infobase_config_file"):
            dir = os.path.dirname(config_file)
            path = os.path.join(dir, config.infobase_config_file)
            config.infobase = yaml.safe_load(open(path).read())

    global query_iter, withKey

    #print "monkeypatching query_iter and withKey functions to talk to database directly."
    load_infogami(config_file)

    query_iter = new_query_iter
    withKey = new_withKey


def main():
    options, keys = parse_options()

    # set query host
    host = web.lstrips(options.server, "http://").strip("/")
    set_query_host(host)

    if options.monkeypatch:
        monkeypatch(options.config)

    # load config
    config.load(options.config)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    update_keys(keys, commit=not options.nocommit)

if __name__ == '__main__':
    main()
