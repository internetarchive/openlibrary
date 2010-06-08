import httplib, re, sys
from openlibrary.catalog.utils.query import query_iter, withKey, has_cover
from lxml.etree import tostring, Element, SubElement
from openlibrary.solr.work_subject import find_subjects, four_types, get_marc_subjects
from pprint import pprint
from urllib import urlopen
import simplejson as json
from time import sleep

re_lang_key = re.compile(r'^/(?:l|languages)/([a-z]{3})$')
re_author_key = re.compile(r'^/(?:a|authors)/(OL\d+A)$')
re_edition_key = re.compile(r'^/(?:b|books)/(OL\d+M)$')

solr_host = {
    'works': 'ia331508:8983',
    'authors': 'ia331509:8983',
    'subjects': 'ia331509:8983',
    'editions': 'ia331509:8983',
}

def is_daisy_encrypted(ia):
    url = 'http://www.archive.org/download/%s/%s_meta.xml' % (ia, ia)
    look_for = '<collection>printdisabled</collection>'
    for attempt in range(20):
        try:
            return any(i.strip().lower() == look_for for i in urlopen(url))
        except:
            print 'retry', attempt
            sleep(5)
    return False

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
        print 'editions:', [e['key'] for e in w['editions']]

    editions = []
    for e in w['editions']:
        pub_year = get_pub_year(e)
        if pub_year:
            e['pub_year'] = pub_year
        if 'ocaid' in e and is_daisy_encrypted(e['ocaid']):
            e['encrypted_daisy'] = True
        editions.append(e)

    editions.sort(key=lambda e: e.get('pub_year', None))

    print len(w['editions']), 'editions found'

    print w['key']
    work_authors = []
    authors = []
    author_keys = []
    for a in w.get('authors', []):
        if 'author' not in a:
            continue
        akey = a['author']['key']
        m = re_author_key.match(akey)
        if not m:
            print 'invalid author key:', akey
            continue
        work_authors.append(akey)
        author_keys.append(m.group(1))
        authors.append(withKey(akey))
    if any(a['type']['key'] == '/type/redirect' for a in authors):
        raise AuthorRedirect
    assert all(a['type']['key'] == '/type/author' for a in authors)

    #subjects = four_types(find_subjects(get_marc_subjects(w)))
    subjects = {}
    field_map = {
        'subjects': 'subject',
        'subject_places': 'place',
        'subject_times': 'time',
        'subject_people': 'people',
    }

    has_fulltext = any(e.get('ocaid', None) and not e.get('encrypted_daisy', None) for e in editions)

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
        print w['key'], subjects['subject']

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
            m = re_lang_key.match(l['key'] if isinstance(l, dict) else l)
            lang.add(m.group(1))
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
#        add_field_list(doc, k + '_facet', subjects[k].keys())
        subject_keys = [str_to_key(s) for s in subjects[k].keys()]
        add_field_list(doc, k + '_key', subject_keys)

    return doc

def solr_update(requests, debug=False, index='works'):
    h1 = httplib.HTTPConnection(solr_host[index])
    h1.connect()
    for r in requests:
        if debug:
            print 'request:', `r[:65]` + '...' if len(r) > 65 else `r`
        assert isinstance(r, basestring)
        url = 'http://%s/solr/%s/update' % (solr_host[index], index)
        print url
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
        if doc is not None:
            add = Element("add")
            add.append(doc)
            add_xml = tostring(add).encode('utf-8')
            requests.append(add_xml)

    return requests

def update_author(akey):
    # http://ia331507.us.archive.org:8984/solr/works/select?indent=on&q=author_key:OL22098A&facet=true&rows=1&sort=edition_count%20desc&fl=title&facet.field=subject_facet&facet.mincount=1
    m = re_author_key.match(akey)
    if not m:
        print 'bad key:', akey
        return
    author_id = m.group(1)
    a = withKey(akey)
    if a['type']['key'] in ('/type/redirect', '/type/delete') or not a.get('name', None):
        return ['<delete><query>key:%s</query></delete>' % author_id] 
    try:
        assert a['type']['key'] == '/type/author'
    except AssertionError:
        print a['type']['key']
        raise

    facet_fields = ['subject', 'time', 'person', 'place']

    url = 'http://' + solr_host['works'] + '/solr/works/select?wt=json&json.nl=arrarr&q=author_key:%s&sort=edition_count+desc&rows=1&fl=title,subtitle&facet=true&facet.mincount=1' % author_id
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

    q = {'type': '/type/redirect', 'location': akey}
    redirects = ''.join('<query>key:%s</query>' % (re_author_key.match(r['key']).group(1),) for r in query_iter(q))
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
