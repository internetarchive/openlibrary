import sys, httplib, re
from time import time
from lxml.etree import tostring, Element
from openlibrary.solr.work_subject import find_subjects

t0 = time
total = 13844390

re_year = re.compile(r'(\d{4})$')
re_edition_key = re.compile('^/b(?:ooks)?/(OL\d+M)$')
re_work_key = re.compile('^/works/(OL\d+W)$')

solr_host = 'localhost:' + sys.argv[1]
update_url = 'http://' + solr_host + '/solr/works/update'
print update_url
def chunk_works(filename, size=2000):
    queue = []
    for line in open(filename):
        if len(line) > 100000000:
            print 'skipping long line:', len(line)
            continue
        queue.append(eval(line))
        if len(queue) == size:
            yield queue
            queue = []
    yield queue

re_bad_char = re.compile('[\x01\x19-\x1e]')
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
    editions = w['editions']
    if len(editions) > 300:
        print `w['title'], len(editions)`
    authors = []
    if 'authors' not in w:
        print 'no authors'
    for a in w['authors']:
        if a is None:
            continue
        cur = {'key': a['key'], 'name': a.get('name', '')}
        if a.get('alternate_names', None):
            cur['alternate_names'] = a['alternate_names']
        authors.append(cur)

    subjects = find_subjects(w, marc_subjects=w['subjects']) if 'subjects' in w else {}

    doc = Element("doc")

    m = re_work_key.match(w['key'])
    add_field(doc, 'key', m.group(1))
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
        m = re_edition_key.match(e['key'])
        if not m:
            print 'bad edition key:', e['key']
            continue
        add_field(doc, 'edition_key', m.group(1))

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
    author_keys = [a['key'] for a in authors]
    assert not any(ak.startswith('/a/') for ak in author_keys)
    author_names = [a.get('name', '') for a in authors]
    assert not any('\t' in n for n in author_names)

    add_field_list(doc, 'author_key', author_keys)
    add_field_list(doc, 'author_name', author_names)

    alt_names = set()
    for a in authors:
        if 'alternate_names' in a:
            alt_names.update(a['alternate_names'])

    add_field_list(doc, 'author_alternative_name', alt_names)
    add_field_list(doc, 'author_facet', (k + '\t' + n for k, n in zip(author_keys, author_names)))
    add_field(doc, 'fiction', subjects['fiction'])

    for k in 'person', 'place', 'subject', 'time':
        if k not in subjects:
            continue
        add_field_list(doc, k, subjects[k].keys())

    for k in 'person', 'place', 'subject', 'time':
        if k not in subjects:
            continue
        add_field_list(doc, k + '_facet', subjects[k].keys())

    for k in 'person', 'place', 'subject', 'time':
        if k not in subjects:
            continue
        add_field_list(doc, k + '_key', (str_to_key(s) for s in subjects[k].keys()))

    return doc

def solr_post(h1, body):
    h1.request('POST', update_url, body.encode('utf-8'), { 'Content-type': 'text/xml;charset=utf-8'})
    return h1.getresponse()

def post_queue(h1, queue):
    add = Element("add")
    for w in queue:
        try:
            doc = build_doc(w)
            if doc is not None:
                add.append(doc)
        except:
            print w
            raise
    add_xml = tostring(add)
    del add
    print add_xml[:60]
    return solr_post(h1, add_xml)

connect = True
if connect:
    h1 = httplib.HTTPConnection(solr_host)
    h1.connect()
    response = solr_post(h1, '<delete><query>*:*</query></delete>')
    response_body = response.read()
    print response.reason
    response = solr_post(h1, '<commit/>')
    response_body = response.read()
    print response.reason

num = 0

filename = sys.argv[2]
print filename
t_prev = time()
for queue in chunk_works(filename):
    num += len(queue)
    percent = (float(num) * 100.0) / total

    if connect:
        response = post_queue(h1, queue)
        response_body = response.read()

    t = time() - t_prev
    rec_per_sec = float(len(queue)) / t
    remain = total - num
    sec_left = float(remain) / rec_per_sec
    if connect:
        print "%d / %d %.2f%%" % (num, total, percent), response.reason, 'rec/sec=%.2f  %.2f hours left' % (rec_per_sec, sec_left / 3600)
    else:
        print "%d / %d %.2f%%" % (num, total, percent), 'rec/sec=%.2f  %.2f mins left' % (rec_per_sec, sec_left / 60)

    if num % 50000 == 0:
        if connect:
            response = solr_post(h1, '<commit/>')
            response_body = response.read()
            print 'commit:', response.reason
    t_prev = time()

if connect:
    response = solr_post(h1, '<commit/>')
    response_body = response.read()
    print response.reason
    response = solr_post(h1, '<optimize/>')
    response_body = response.read()
    print response.reason
