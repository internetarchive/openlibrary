from openlibrary.catalog.utils.query import query_iter, withKey
import httplib, re, sys
from lxml.etree import tostring, Element

re_bad_char = re.compile('[\x1a-\x1e]')
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

def build_doc(wkey):
    w = withKey(wkey)
    editions = list(query_iter({'type':'/type/edition', 'works': wkey, '*': None}))
    authors = [withKey(a['author']['key']) for a in w['authors']]

    doc = Element("doc")

    add_field(doc, 'key', w['key'])
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
    add_field(doc, 'alternative_subtitle', alt_subtitles)

    add_field(doc, 'edition_count', len(editions))
    for e in editions:
        add_field(doc, 'edition_key', e['key'])

    fields = ('by_statement', 'publish_date')
    for k in fields:
        found = set( e[k] for e in editions if e.get(k, None))
        add_field_list(doc, k, found)

    k = 'first_sentence'
    fs = set( e[k]['value'] if isinstance(e[k], dict) else e[k] for e in editions if e.get(k, None))
    add_field_list(doc, k, fs)

    field_map = [
        ('lccn', 'lccn'),
        ('publishers', 'publisher'),
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
        if db_key == 'publishers':
            add_field_list(doc, search_key + '_facet', v)


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

    v = set( e['ocaid'] for e in editions if 'ocaid' in e)
    add_field_list(doc, 'ia', v)
    author_keys = [a['key'] for a in authors]
    author_names = [a['name'] for a in authors]
    add_field_list(doc, 'author_key', author_keys)
    add_field_list(doc, 'author_name', author_names)

    alt_names = set()
    for a in authors:
        if 'alternate_names' not in a:
            continue
        alt_names.update(a['alternate_names'])

    add_field_list(doc, 'author_alternative_name', alt_names)
    add_field_list(doc, 'author_facet', (`v` for v in zip(author_keys, author_names)))

    return doc

def solr_update(requests, debug=False):
    solr_host = 'localhost:8985'
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


def update_work(wkey, debug=False):
    add = Element("add")
    add.append(build_doc(wkey))
    add_xml = tostring(add, pretty_print=True).encode('utf-8')

    q = {'type': '/type/redirect', 'location': wkey}
    redirects = ''.join('<query>key:%s</query>' % r['key'] for r in query_iter(q))
    delete_xml = '<delete><query>key:%s</query>%s</delete>' % (wkey, redirects)
    requests = [delete_xml, add_xml]
    solr_update(requests, debug)

def commit_and_optimize(debug=False):
    requests = ['<commit />', '<optimize />']
    solr_update(requests, debug)

if __name__ == '__main__':
    key = sys.argv[1]
    print key
    update_work(key, debug=True)
    commit_and_optimize(debug=True)
