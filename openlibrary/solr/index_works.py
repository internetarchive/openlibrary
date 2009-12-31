from lxml.etree import tostring, Element
import sys, httplib, re
from time import time
import re, urllib2

from openlibrary.catalog.importer.db_read import get_mc
from openlibrary.catalog.get_ia import get_data
from openlibrary.catalog.marc.fast_parse import get_tag_lines, get_all_subfields, get_subfield_values, get_subfields, BadDictionary
from openlibrary.catalog.utils import remove_trailing_dot, remove_trailing_number_dot, flip_name
from collections import defaultdict

t0 = time
total = 13900000

re_year = re.compile(r'(\d{4})$')
re_edition_key = re.compile('^/b(?:ooks)?/(OL\d+M)$')
re_author_key = re.compile('^/a(?:uthors)?/(OL\d+A)$')
re_work_key = re.compile('^/works/(OL\d+W)$')

solr_host = 'localhost:' + sys.argv[1]
update_url = 'http://' + solr_host + '/solr/works/update'
def chunk_works(filename, size=2000):
    queue = []
#    num = 0
    for line in open(filename):
#        num += 1
#        if num % 10000 == 0:
#            percent = (float(num) * 100.0) / total
#            print "%d %.2f%%" % (num, percent)
#        if num < 1540000:
#            continue
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

re_ia_marc = re.compile('^(?:.*/)?([^/]+)_(marc\.xml|meta\.mrc)(:0:\d+)?$')
def get_marc_source(w):
    found = set()
    for e in w['editions']:
        sr = e.get('source_record', [])
        if sr:
            found.update(i[5:] for i in sr if i.startswith('marc:'))
        else:
            mc = get_mc(e['key'])
            if mc and not mc.startswith('amazon:') and not re_ia_marc.match(mc):
                found.add(mc)
    return found

subject_fields = set(['600', '610', '611', '630', '648', '650', '651', '662'])

def get_marc_subjects(w):
    for src in get_marc_source(w):
        data = None
        try:
            data = get_data(src)
        except ValueError:
            print 'bad record source:', src
            print 'http://openlibrary.org' + w['key']
            continue
        except urllib2.HTTPError, error:
            print 'HTTP error:', error.code, error.msg
            print 'http://openlibrary.org' + w['key']
        if not data:
            continue
        try:
            lines = list(get_tag_lines(data, subject_fields))
        except BadDictionary:
            print 'bad dictionary:', src
            print 'http://openlibrary.org' + w['key']
            continue
        yield lines

# 'Rhodes, Dan (Fictitious character)'
re_fictitious_character = re.compile('^(.+), (.+)( \(Fictitious character\))$')

def tidy_subject(s):
    s = remove_trailing_dot(s)
    m = re_fictitious_character.match(s)
    return m.group(2) + ' ' + m.group(1) + m.group(3) if m else s

re_comma = re.compile('^(.+), (.+)$')
def flip_place(s):
    s = remove_trailing_dot(s)
    m = re_comma.match(s)
    return m.group(2) + ' ' + m.group(1) if m else s

# 'Ram Singh, guru of Kuka Sikhs'
re_flip_name = re.compile('^(.+), ([A-Z].+)$')

def find_subjects(w):

    people = defaultdict(int)
    genres = defaultdict(int)
    when = defaultdict(int)
    place = defaultdict(int)
    subject = defaultdict(int)
    fiction = False
    for lines in get_marc_subjects(w):
        for tag, line in lines:
            if tag == '600':
                name_and_date = []
                for k, v in get_subfields(line, ['a', 'b', 'c', 'd']):
                    v = '(' + remove_trailing_number_dot(v) + ')' if k == 'd' else v.strip(' /,;:')
                    if k == 'a':
                        m = re_flip_name.match(v)
                        if m and v != 'Mao, Zedong':
                            v = flip_name(v)
                    name_and_date.append(v)
                people[remove_trailing_dot(' '.join(name_and_date))] += 1
            if tag == '650':
                for v in get_subfield_values(line, ['a']):
                    subject[tidy_subject(v)] += 1
            if tag == '651':
                for v in get_subfield_values(line, ['a']):
                    place[flip_place(v)] += 1

            for v in get_subfield_values(line, ['y']):
                when[remove_trailing_dot(v)] += 1
            for v in get_subfield_values(line, ['v']):
                subject[remove_trailing_dot(v)] += 1
            for v in get_subfield_values(line, ['z']):
                place[flip_place(v)] += 1
            for v in get_subfield_values(line, ['x']):
                subject[tidy_subject(v)] += 1

            v_and_x = get_subfield_values(line, ['v', 'x'])
            if 'Fiction' in v_and_x or 'Fiction.' in v_and_x:
                fiction = True
    if 'Fiction' in subject:
        del subject['Fiction']
    ret = {
        'fiction': fiction,
    }
    if people:
        ret['person'] = dict(people)
    if when:
        ret['time'] = dict(when)
    if place:
        ret['place'] = dict(place)
    if subject:
        ret['subject'] = dict(subject)
    return ret

def build_doc(w):
    editions = w['editions']
    if len(editions) > 300:
        print `w['title'], len(editions)`
    authors = [eval(a) for a in w['author'] if a is not None]
    if not authors:
        return

    subjects = find_subjects(w)

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

    v = set( e['ocaid'].strip() for e in editions if 'ocaid' in e)
    add_field_list(doc, 'ia', v)

    author_keys = [a['key'] for a in authors]
    author_names = [a.get('name', '') for a in authors]

    for akey in author_keys:
        m = re_author_key.match(akey)
        if not m:
            print 'bad author key:', akey
            continue
        add_field(doc, 'author_key', m.group(1))

    add_field_list(doc, 'author_name', author_names)

    alt_names = set()
    for a in authors:
        if 'alternate_names' not in a:
            continue
        alt_names.update(a['alternate_names'])

    add_field_list(doc, 'author_alternative_name', alt_names)
    add_field_list(doc, 'author_facet', (`v` for v in zip(author_keys, author_names)))
    add_field(doc, 'fiction', subjects['fiction'])

    for k in 'person', 'place', 'subject', 'time':
        if k not in subjects:
            continue
        add_field_list(doc, k, subjects[k].keys())
    return doc

def solr_post(h1, body):
    h1.request('POST', update_url, body, { 'Content-type': 'text/xml;charset=utf-8'})
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
    add_xml = tostring(add, pretty_print=True).encode('utf-8')
    del add
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
        print "%d %.2f%%" % (num, percent), response.reason, 'rec/sec=%.2f  %.2f hours left' % (rec_per_sec, sec_left / 3600)
    else:
        print "%d %.2f%%" % (num, percent), 'rec/sec=%.2f  %.2f mins left' % (rec_per_sec, sec_left / 60)

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
