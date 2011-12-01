import httplib, re, sys
from openlibrary.catalog.utils.query import query_iter, withKey, has_cover
#from openlibrary.catalog.marc.marc_subject import get_work_subjects, four_types
from lxml.etree import tostring, Element, SubElement
from pprint import pprint
from urllib2 import urlopen, URLError, HTTPError
import simplejson as json
from time import sleep
from openlibrary import config
from unicodedata import normalize
from collections import defaultdict
from openlibrary.utils.isbn import opposite_isbn

re_lang_key = re.compile(r'^/(?:l|languages)/([a-z]{3})$')
re_author_key = re.compile(r'^/(?:a|authors)/(OL\d+A)')
re_edition_key = re.compile(r'^/(?:b|books)/(OL\d+M)$')

solr_host = {}

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
    url = 'http://www.archive.org/download/%s/%s_meta.xml' % (ia, ia)
    #print 'getting:', url
    matches = {'boxid': set(), 'collection': set() }
    for attempt in range(5):
        try:
            for line in urlopen(url):
                m = re_collection.search(line)
                if m:
                    matches[m.group(1).lower()].add(m.group(2).lower())
            return matches
        except URLError:
            print 'retry', attempt, url
            sleep(5)
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

re_solr_field = re.compile('^[-\w]+$', re.U)

def build_doc(w, obj_cache={}, resolve_redirects=False):
    wkey = w['key']
    assert w['type']['key'] == '/type/work'
    title = w.get('title', None)
    if not title:
        return

    def get_pub_year(e):
        pub_date = e.get('publish_date', None)
        if pub_date:
            m = re_iso_date.match(pub_date)
            if m:
                return m.group(1)
            m = re_year.search(pub_date)
            if m:
                return m.group(1)

    if 'editions' not in w:
        q = { 'type':'/type/edition', 'works': wkey, '*': None }
        w['editions'] = list(query_iter(q))
        #print 'editions:', [e['key'] for e in w['editions']]

    identifiers = defaultdict(list)

    editions = []
    for e in w['editions']:
        pub_year = get_pub_year(e)
        if pub_year:
            e['pub_year'] = pub_year
        ia = None
        if 'ocaid' in e:
            ia = e['ocaid']
        elif 'ia_loaded_id' in e:
            loaded = e['ia_loaded_id']
            ia = loaded if isinstance(loaded, basestring) else loaded[0]
        if ia:
            ia_meta_fields = get_ia_collection_and_box_id(ia)
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

    #print len(w['editions']), 'editions found'

    #print w['key']
    work_authors = []
    authors = []
    author_keys = []
    for a in w.get('authors', []):
        if 'author' not in a: # OL Web UI bug
            continue # http://openlibrary.org/works/OL15365167W.yml?m=edit&v=1
        akey = a['author']['key']
        m = re_author_key.match(akey)
        if not m:
            print 'invalid author key:', akey
            continue
        work_authors.append(akey)
        author_keys.append(m.group(1))
        if akey in obj_cache and obj_cache[akey]['type']['key'] != '/type/redirect':
            authors.append(obj_cache[akey])
        else:
            authors.append(withKey(akey))
    if any(a['type']['key'] == '/type/redirect' for a in authors):
        if resolve_redirects:
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

    has_fulltext = any(e.get('ocaid', None) or e.get('overdrive', None) for e in editions)

    #print 'has_fulltext:', has_fulltext

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

    doc = Element("doc")

    add_field(doc, 'key', w['key'][7:])
    title = w.get('title', None)
    if title:
        add_field(doc, 'title', title)
#        add_field(doc, 'title_suggest', title)

    add_field(doc, 'has_fulltext', has_fulltext)
    if w.get('subtitle', None):
        add_field(doc, 'subtitle', w['subtitle'])

    alt_titles = set()
    for e in editions:
        if 'title' in e and e['title'] != title:
            alt_titles.add(e['title'])
        for f in 'work_titles', 'other_titles':
            for t in e.get(f, []):
                if t != title:
                    alt_titles.add(t)
    add_field_list(doc, 'alternative_title', alt_titles)

    alt_subtitles = set( e['subtitle'] for e in editions if e.get('subtitle', None) and e['subtitle'] != w.get('subtitle', None))
    add_field_list(doc, 'alternative_subtitle', alt_subtitles)

    add_field(doc, 'edition_count', len(editions))
    for e in editions:
        add_field(doc, 'edition_key', re_edition_key.match(e['key']).group(1))

    cover_edition = pick_cover(w, editions)
    if cover_edition:
        add_field(doc, 'cover_edition_key', re_edition_key.match(cover_edition).group(1))
    if w.get('covers'):
        cover = w['covers'][0]
        assert isinstance(cover, int)
        add_field(doc, 'cover_i', cover)

    k = 'by_statement'
    add_field_list(doc, k, set( e[k] for e in editions if e.get(k, None)))

    k = 'publish_date'
    pub_dates = set(e[k] for e in editions if e.get(k, None))
    add_field_list(doc, k, pub_dates)
    pub_years = set(m.group(1) for m in (re_year.search(i) for i in pub_dates) if m)
    if pub_years:
        add_field_list(doc, 'publish_year', pub_years)
        add_field(doc, 'first_publish_year', min(int(i) for i in pub_years))

    k = 'first_sentence'
    fs = set( e[k]['value'] if isinstance(e[k], dict) else e[k] for e in editions if e.get(k, None))
    add_field_list(doc, k, fs)

    publishers = set()
    for e in editions:
        publishers.update('Sine nomine' if is_sine_nomine(i) else i for i in e.get('publishers', []))
    add_field_list(doc, 'publisher', publishers)
#    add_field_list(doc, 'publisher_facet', publishers)

    field_map = [
        ('lccn', 'lccn'),
        ('publish_places', 'publish_place'),
        ('oclc_numbers', 'oclc'),
        ('contributions', 'contributor'),
    ]

    for db_key, search_key in field_map:
        v = set()
        for e in editions:
            if db_key not in e:
                continue
            v.update(e[db_key])
        add_field_list(doc, search_key, v)

    isbn = set()
    for e in editions:
        for f in 'isbn_10', 'isbn_13':
            for v in e.get(f, []):
                v = v.replace('-', '')
                isbn.add(v)
                alt = opposite_isbn(v)
                if alt:
                    isbn.add(alt)
    add_field_list(doc, 'isbn', isbn)

    lang = set()
    ia_loaded_id = set()
    ia_box_id = set()

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
    #print 'lending_edition:', lending_edition
    ia_list = list(pub_nongoog) + list(pub_goog) + list(nonpub_nongoog) + list(nonpub_goog)
    add_field_list(doc, 'ia', ia_list)
    if has_fulltext:
        add_field(doc, 'public_scan_b', public_scan)
    if all_collection:
        add_field(doc, 'ia_collection_s', ';'.join(all_collection))
    if all_overdrive:
        add_field(doc, 'overdrive_s', ';'.join(all_overdrive))
    if lending_edition:
        add_field(doc, 'lending_edition_s', lending_edition)
    elif in_library_edition:
        add_field(doc, 'lending_edition_s', in_library_edition)
    if printdisabled:
        add_field(doc, 'printdisabled_s', ';'.join(list(printdisabled)))
        
    if lending_edition or in_library_edition:
        add_field(doc, "borrowed_b", is_borrowed(lending_edition or in_library_edition))

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
    h1 = httplib.HTTPConnection(get_solr(index))
    h1.connect()
    for r in requests:
        if debug:
            print 'request:', `r[:65]` + '...' if len(r) > 65 else `r`
        assert isinstance(r, basestring)
        url = 'http://%s/solr/%s/update' % (get_solr(index), index)
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

def update_work(w, obj_cache={}, debug=False, resolve_redirects=False):
    wkey = w['key']
    assert wkey.startswith('/works')
    assert '/' not in wkey[7:]
    q = {'type': '/type/redirect', 'location': wkey}
    redirect_keys = [r['key'][7:] for r in query_iter(q)]
    redirects = ''.join('<query>key:%s</query>' % r for r in redirect_keys if '/' not in r)
    delete_xml = '<delete><query>key:%s</query>%s</delete>' % (wkey[7:], redirects)
    requests = [delete_xml]

    if w['type']['key'] == '/type/work' and w.get('title'):
        try:
            doc = build_doc(w, obj_cache, resolve_redirects=resolve_redirects)
        except:
            print w
            raise
        if doc is not None:
            add = Element("add")
            add.append(doc)
            add_xml = tostring(add).encode('utf-8')
            requests.append(add_xml)

    return requests

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

    url = 'http://' + get_solr('works') + '/solr/works/select?wt=json&json.nl=arrarr&q=author_key:%s&sort=edition_count+desc&rows=1&fl=title,subtitle&facet=true&facet.mincount=1' % author_id
    url += ''.join('&facet.field=%s_facet' % f for f in facet_fields)
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
    
def main(keys):
    requests = []
    for k in keys:
        w = withKey(key)
        requests += update_work(w, debug=True)
    requests += ['<commit />']
    solr_update(requests, debug=True)
        
if __name__ == '__main__':
    keys = sys.argv[1:]
    main(keys)