import httplib, re, sys
from openlibrary.catalog.utils.query import query_iter, withKey, has_cover
from lxml.etree import tostring, Element, SubElement
from openlibrary.solr.work_subject import find_subjects, four_types, get_marc_subjects
from pprint import pprint
from urllib import urlopen
import simplejson as json

solr_host = {
    'works': 'ia331507:8983',
    'authors': 'ia331507:8984'
}

class AuthorRedirect (Exception):
    pass

re_bad_char = re.compile('[\x01\x1a-\x1e]')
re_year = re.compile(r'(\d{4})$')
def strip_bad_char(s):
    if not isinstance(s, basestring):
        return s
    return re_bad_char.sub('', s)

def add_field(doc, name, value):
    field = Element("field", name=name)
    try:
        field.text = unicode(strip_bad_char(value))
    except:
        print `value`
        raise
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

def pick_cover(editions):
    first_with_cover = None
    for e in editions:
        if not has_cover(e['key']):
            continue
        if not first_with_cover:
            first_with_cover = e['key']
        for l in e.get('languages', []):
            if 'eng' in l:
                return e['key']
    return first_with_cover

def build_doc(w):
    wkey = w['key']
    assert w['type']['key'] == '/type/work'
    title = w.get('title', None)
    if not title:
        return

    def get_pub_year(e):
        pub_date = e.get('publish_date', None)
        if pub_date:
            m = re_year.search(pub_date)
            if m:
                return m.group(1)

    if 'editions' not in w:
        q = { 'type':'/type/edition', 'works': wkey, '*': None }
        w['editions'] = list(query_iter(q))

    editions = []
    for e in w['editions']:
        pub_year = get_pub_year(e)
        if pub_year:
            e['pub_year'] = pub_year
        editions.append(e)

    editions.sort(key=lambda e: e.get('pub_year', None))

    print len(w['editions']), 'editions found'

    try:
        work_authors = [a['author']['key'] for a in w.get('authors', []) if 'author' in a]
        author_keys = [akey[3:] for akey in work_authors]
        authors = [withKey(akey) for akey in work_authors]
    except KeyError:
        print w['key']
        raise
    print w['key']
    for a in authors:
        print a
    if any(a['type']['key'] == '/type/redirect' for a in authors):
        raise AuthorRedirect
    assert all(a['type']['key'] == '/type/author' for a in authors)

    subjects = four_types(find_subjects(get_marc_subjects(w)))
    print subjects

    doc = Element("doc")

    add_field(doc, 'key', w['key'][7:])
    title = w.get('title', None)
    if title:
        add_field(doc, 'title', title)
#        add_field(doc, 'title_suggest', title)
    has_fulltext = any(e.get('ocaid', None) for e in editions)

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
        add_field(doc, 'edition_key', e['key'][3:])

    cover_edition = None
    if 'cover_edition' in w:
        cover_edition = w['cover_edition']['key']
    else:
        cover_edition = pick_cover(editions)
    if cover_edition:
        add_field(doc, 'cover_edition_key', cover_edition[3:])

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
                isbn.add(v.replace('-', ''))
    add_field_list(doc, 'isbn', isbn)

    lang = set()
    for e in editions:
        for l in e.get('languages', []):
            assert l['key'].startswith('/l/') and len(l['key']) == 6
            lang.add(l['key'][3:])
    if lang:
        add_field_list(doc, 'language', lang)

    goog = set() # google
    non_goog = set()
    for e in editions:
        if 'ocaid' in e:
            assert isinstance(e['ocaid'], basestring)
            i = e['ocaid'].strip()
            if i.endswith('goog'):
                goog.add(i)
            else:
                non_goog.add(i)
    add_field_list(doc, 'ia', list(non_goog) + list(goog))
    author_keys = [a['key'][3:] for a in authors]
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
#        add_field_list(doc, k + '_facet', subjects[k].keys())
        subject_keys = [str_to_key(s) for s in subjects[k].keys()]
        add_field_list(doc, k + '_key', subject_keys)

    return doc

def solr_update(requests, debug=False, index='works'):
    h1 = httplib.HTTPConnection(solr_host[index])
    h1.connect()
    for r in requests:
        if debug:
            print `r[:70]` + '...' if len(r) > 70 else `r`
        url = 'http://%s/solr/%s/update' % (solr_host[index], index)
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

def update_work(w):
    wkey = w['key']
    assert wkey.startswith('/works')
    assert '/' not in wkey[7:]
    q = {'type': '/type/redirect', 'location': wkey}
    redirect_keys = [r['key'][7:] for r in query_iter(q)]
    redirects = ''.join('<query>key:%s</query>' % r for r in redirect_keys if '/' not in r)
    delete_xml = '<delete><query>key:%s</query>%s</delete>' % (wkey[7:], redirects)
    requests = [delete_xml]

    if w['type']['key'] == '/type/work' and w.get('title', None):
        try:
            doc = build_doc(w)
        except:
            print w
            raise
        if doc:
            add = Element("add")
            add.append(build_doc(w))
            add_xml = tostring(add).encode('utf-8')
            requests.append(add_xml)

    return requests

def update_author(akey):
    # http://ia331507.us.archive.org:8984/solr/works/select?indent=on&q=author_key:OL22098A&facet=true&rows=1&sort=edition_count%20desc&fl=title&facet.field=subject_facet&facet.mincount=1
    a = withKey(akey)
    if a['type']['key'] in ('/type/redirect', '/type/delete') or not a.get('name', None):
        return ['<delete><query>key:%s</query></delete>' % akey[3:]] 
    try:
        assert a['type']['key'] == '/type/author'
    except AssertionError:
        print a['type']['key']
        raise

    facet_fields = ['subject', 'time', 'person', 'place']
    url = 'http://' + solr_host['works'] + '/solr/works/select?wt=json&json.nl=arrarr&q=author_key:%s&sort=edition_count+desc&rows=1&fl=title,subtitle&facet=true&facet.mincount=1' % akey[3:]
    url += ''.join('&facet.field=%s_facet' % f for f in facet_fields)
    print url
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
    add_field(doc, 'key', akey[3:])
    if a.get('name', None):
        add_field(doc, 'name', a['name'])
    for f in 'birth_date', 'death_date', 'date':
        if a.get(f, None):
            add_field(doc, f, a[f])
    if top_work:
        add_field(doc, 'top_work', top_work)
    add_field(doc, 'work_count', work_count)
    add_field_list(doc, 'top_subjects', top_subjects)

    q = {'type': '/type/redirect', 'location': akey}
    redirects = ''.join('<query>key:%s</query>' % r['key'][3:] for r in query_iter(q))
    requests = []
    if redirects:
        requests.append('<delete>' + redirects + '</delete>')

    requests.append(tostring(add).encode('utf-8'))
    return requests

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
