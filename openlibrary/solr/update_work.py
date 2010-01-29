import httplib, re, sys
from openlibrary.catalog.utils.query import query_iter, withKey
from lxml.etree import tostring, Element
from openlibrary.solr.work_subject import find_subjects
from pprint import pprint

re_bad_char = re.compile('[\x1a-\x1e]')
re_year = re.compile(r'(\d{4})$')
def strip_bad_char(s):
    if not isinstance(s, basestring):
        return s
    return re_bad_char.sub('', s)

def add_field(doc, name, value):
    field = Element("field", name=name)
    field.text = unicode(strip_bad_char(value))
    doc.append(field)

def add_field_list(doc, name, field_list):
    for value in field_list:
        add_field(doc, name, value)

to_drop = set('''!*"'();:@&=+$,/?%#[]''')

def str_to_key(s):
    return ''.join(c for c in s.lower() if c not in to_drop)

re_not_az = re.compile('[^a-zA-Z]')
def is_sine_nomine(pub):
    return re_not_az.sub('', pub).lower() == 'sn'

def build_doc(w):
    wkey = w['key']
    assert w['type']['key'] == '/type/work'

    if 'editions' in w:
        editions = w['editions']
    else:
        q = { 'type':'/type/edition', 'works': wkey, '*': None }
        editions = list(query_iter(q))
        w['editions'] = editions

    print len(w['editions']), 'editions found'

    author_keys = [a['author']['key'][3:] for a in w.get('authors', [])]
    authors = [withKey(a['author']['key']) for a in w.get('authors', [])]

    subjects = find_subjects(w)

    doc = Element("doc")

    add_field(doc, 'key', w['key'][7:])
    add_field(doc, 'title', w['title'])
    add_field(doc, 'title_suggest', w['title'])
    has_fulltext = any(e.get('ocaid', None) for e in editions)

    add_field(doc, 'has_fulltext', has_fulltext)
    if w.get('subtitle', None):
        add_field(doc, 'subtitle', w['subtitle'])

    alt_titles = set()
    for e in editions:
        if 'title' in e and e['title'] != w['title']:
            alt_titles.add(e['title'])
        for f in 'work_titles', 'other_titles':
            for t in e.get(f, []):
                if t != w['title']:
                    alt_titles.add(t)
    add_field_list(doc, 'alternative_title', alt_titles)

    alt_subtitles = set( e['subtitle'] for e in editions if e.get('subtitle', None) and e['subtitle'] != w.get('subtitle', None))
    add_field_list(doc, 'alternative_subtitle', alt_subtitles)

    add_field(doc, 'edition_count', len(editions))
    for e in editions:
        add_field(doc, 'edition_key', e['key'][3:])

    if 'cover_edition' in w:
        print 'cover edition:', w['cover_edition']['key'][3:]
        add_field(doc, 'cover_edition_key', w['cover_edition']['key'][3:])

    k = 'by_statement'
    add_field_list(doc, k, set( e[k] for e in editions if e.get(k, None)))

    k = 'publish_date'
    pub_dates = set(e[k] for e in editions if e.get(k, None))
    add_field_list(doc, k, pub_dates)
    pub_years = set(m.group(1) for m in (re_year.match(i) for i in pub_dates) if m)
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
    add_field_list(doc, 'publisher_facet', publishers)

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
                isbn.add(v.replace('-', ''))
    add_field_list(doc, 'isbn', isbn)

    lang = set()
    for e in editions:
        for l in e.get('languages', []):
            assert l['key'].startswith('/l/') and len(l['key']) == 6
            lang.add(l['key'][3:])
    if lang:
        add_field_list(doc, 'language', lang)

    v = set( e['ocaid'].strip() for e in editions if 'ocaid' in e)
    add_field_list(doc, 'ia', v)
    author_keys = [a['key'][3:] for a in authors]
    author_names = [a.get('name', '') for a in authors]
    add_field_list(doc, 'author_key', author_keys)
    add_field_list(doc, 'author_name', author_names)

    alt_names = set()
    for a in authors:
        if 'alternate_names' in a:
            alt_names.update(a['alternate_names'])

    add_field_list(doc, 'author_alternative_name', alt_names)
    add_field_list(doc, 'author_facet', (`v` for v in zip(author_keys, author_names)))
    #if subjects:
    #    add_field(doc, 'fiction', subjects['fiction'])

    facet_map = {
        'person': 'people',
        'place': 'places',
        'subject': 'subjects',
        'time': 'times',
    }
    for k in 'person', 'place', 'subject', 'time':
        k2 = facet_map[k]
        if k2 not in subjects:
            continue
        add_field_list(doc, k, subjects[k2].keys())

    for k in 'person', 'place', 'subject', 'time':
        k2 = facet_map[k]
        if k2 not in subjects:
            continue
        add_field_list(doc, k + '_facet', subjects[k2].keys())

    for k in 'person', 'place', 'subject', 'time':
        k2 = facet_map[k]
        if k2 not in subjects:
            print k2, 'not in', subjects.keys()
            continue
        subject_keys = [str_to_key(s) for s in subjects[k2].keys()]
        print 'subject keys:', subject_keys
        add_field_list(doc, k + '_key', subject_keys)

    return doc

def solr_update(requests, debug=False):
    solr_host = 'localhost:8986'
    h1 = httplib.HTTPConnection(solr_host)
    h1.connect()
    for r in requests:
        if debug:
            print `r[:70]` + '...' if len(r) > 70 else `r`
        h1.request('POST', 'http://' + solr_host + '/solr/works/update', r, { 'Content-type': 'text/xml;charset=utf-8'})
        response = h1.getresponse()
        response_body = response.read()
        if debug:
            print response.reason
#            print response_body
#            print response.getheaders()
    h1.close()


def update_work(w, debug=False):
    wkey = w['key']
    assert wkey.startswith('/works')
    q = {'type': '/type/redirect', 'location': wkey}
    redirects = ''.join('<query>key:%s</query>' % r['key'][7:] for r in query_iter(q))
    delete_xml = '<delete><query>key:%s</query>%s</delete>' % (wkey[7:], redirects)
    requests = [delete_xml]

    if w['type']['key'] == '/type/work':
        add = Element("add")
        add.append(build_doc(w))
        add_xml = tostring(add).encode('utf-8')
        requests.append(add_xml)

    solr_update(requests, debug)

def commit_and_optimize(debug=False):
    requests = ['<commit />', '<optimize />']
    solr_update(requests, debug)

if __name__ == '__main__':
    key = sys.argv[1]
    print key
    w = withKey(key)
    update_work(w, debug=True)
    requests = ['<commit />']
    solr_update(requests, debug=True)
