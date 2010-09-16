import sys, codecs, re, web, httplib
sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
from time import time
from lxml.etree import tostring, Element
from openlibrary.solr.work_subject import find_subjects, four_types

db = web.database(dbn='mysql', db='openlibrary', user='root', passwd='') # , charset='utf8')
db.printing = False

re_year = re.compile(r'(\d{4})$')
re_author_key = re.compile('^/a/OL(\d+)A$')
re_work_key = re.compile('^/works/OL(\d+)W$')

covers = {}
for line in open('../work_covers/list'):
    i, j = line[:-1].split(' ')
    covers[int(i)] = int(j)

connect = False
connect = True

long_subjects = set([11369047, 11388034, 11404100, 11408860, 12548230, 7623678])

solr_host = 'localhost:8983'
update_url = 'http://' + solr_host + '/solr/works/update'

def work_subjects(wkey):
    ret = db.query('select subjects as s from work_subject where work=$wkey', vars=locals())
    if not ret:
        return
    return eval(ret[0].s)

to_drop = set(''';/?:@&=+$,<>#%"{}|\\^[]`\n\r''')

def str_to_key(s):
    return ''.join(c if c != ' ' else '_' for c in s.lower() if c not in to_drop)

def solr_post(h1, body):
    if not connect:
        return 'not connected'
    h1.request('POST', update_url, body, { 'Content-type': 'text/xml;charset=utf-8'})
    response = h1.getresponse()
    response.read()
    return response.reason

h1 = None
if connect:
    h1 = httplib.HTTPConnection(solr_host)
    h1.connect()
    print solr_post(h1, '<delete><query>*:*</query></delete>')
    print solr_post(h1, '<commit/>')
    print solr_post(h1, '<optimize/>')

def add_field(doc, name, value):
    field = Element("field", name=name)
    field.text = unicode(strip_bad_char(value))
    doc.append(field)

def add_field_list(doc, name, field_list):
    for value in field_list:
        add_field(doc, name, value)

re_bad_char = re.compile('[\x01\x19-\x1e]')
def strip_bad_char(s):
    if not isinstance(s, basestring):
        return s
    return re_bad_char.sub('', s)

re_not_az = re.compile('[^a-zA-Z]')
def is_sine_nomine(pub):
    return re_not_az.sub('', pub).lower() == 'sn'

def build_doc(w):
    wkey = w['key']

    m = re_work_key.match(wkey)
    wkey_num = int(m.group(1))
    if wkey_num in long_subjects:
        return

    def get_pub_year(e):
        pub_date = e.get('publish_date', None)
        if pub_date:
            m = re_year.search(pub_date)
            if m:
                return m.group(1)
    editions = []
    for e in w['editions']:
        pub_year = get_pub_year(e)
        if pub_year:
            e['pub_year'] = pub_year
        editions.append(e)

    editions.sort(key=lambda e: e.get('pub_year', None))

    doc = Element("doc")
    add_field(doc, 'key', 'OL%dW' % wkey_num)
    add_field(doc, 'title', w['title'])
    #add_field(doc, 'title_suggest', w['title'])

    has_fulltext = any(e.get('ia', None) for e in editions)
    add_field(doc, 'has_fulltext', has_fulltext)
    if w.get('subtitle', None):
        add_field(doc, 'subtitle', w['subtitle'])

    alt_titles = set()
    for e in editions:
        if e.get('title', None):
            t = e['title']
            if t != w['title']:
                alt_titles.add(t)
        for f in 'work_titles', 'other_titles':
            if f not in e:
                continue
            assert isinstance(e[f], list)
            for t in e[f]:
                if t != w['title']:
                    alt_titles.add(t)

    add_field_list(doc, 'alternative_title', alt_titles)

    alt_subtitles = set( e['subtitle'] for e in editions if e.get('subtitle', None) and e['subtitle'] != w.get('subtitle', None))
    add_field(doc, 'alternative_subtitle', alt_subtitles)

    add_field(doc, 'edition_count', len(editions))
    for e in editions:
        add_field(doc, 'edition_key', 'OL%dM' % e['ekey'])
    if wkey_num in covers:
        add_field(doc, 'cover_edition_key', 'OL%dM' % covers[wkey_num])

    k = 'by_statement'
    add_field_list(doc, k, set( e[k] for e in editions if e.get(k, None)))

    k = 'publish_date'
    pub_dates = set(e[k] for e in editions if e.get(k, None))
    add_field_list(doc, k, pub_dates)
    pub_years = set(e['pub_year'] for e in editions if 'pub_year' in e)
    if pub_years:
        add_field_list(doc, 'publish_year', pub_years)
        add_field(doc, 'first_publish_year', min(int(i) for i in pub_years))

    k = 'first_sentence'
    fs = set( e[k] for e in editions if e.get(k, None))
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
            if db_key == 'publishers':
                e[db_key] = ['Sine nomine' if is_sine_nomine(i) else i for i in e[db_key].split('\t')]
            assert isinstance(e[db_key], list)
            v.update(e[db_key])
        add_field_list(doc, search_key, v)
#        if db_key == 'publishers':
#            add_field_list(doc, search_key + '_facet', v)

    isbn = set()
    for e in editions:
        for f in 'isbn_10', 'isbn_13':
            if f not in e:
                continue
            assert isinstance(e[f], list)
            for v in e[f]:
                isbn.add(v.replace('-', ''))
    add_field_list(doc, 'isbn', isbn)

    lang = set()
    for e in editions:
        if 'languages' not in e:
            continue
        assert isinstance(e['languages'], list)
        for l in e['languages']:
            for l2 in l.split('\t'):
                if len(l2) != 3:
                    print e['languages']
                
                assert len(l2) == 3
                lang.add(l2)
    if lang:
        add_field_list(doc, 'language', lang)

    goog = set() # google
    non_goog = set()
    for e in editions:
        if 'ia' in e:
            assert isinstance(e['ia'], list)
            for i in e['ia']:
                i = i.strip()
                if i.endswith('goog'):
                    goog.add(i)
                else:
                    non_goog.add(i)
    add_field_list(doc, 'ia', list(non_goog) + list(goog))

    authors = w['authors']
    author_keys = ['OL%dA' % a['akey'] for a in authors]
    author_names = [a.get('name', '') or '' for a in authors]

    add_field_list(doc, 'author_key', author_keys)
    add_field_list(doc, 'author_name', author_names)

    alt_names = set()
    for a in authors:
        if 'alt_names' not in a:
            continue
        assert isinstance(a['alt_names'], list)
        alt_names.update(a['alt_names'])

    add_field_list(doc, 'author_alternative_name', alt_names)
    add_field_list(doc, 'author_facet', (' '.join(v) for v in zip(author_keys, author_names)))

#    if 'subjects' in w:
#        if isinstance(w['subjects'][0], list):
#            try:
#                subjects = find_subjects(w['subjects'])
#            except ValueError:
#                print w['subjects']
#                raise
#        else:
#            subjects = work_subjects(wkey_num)
#            if not subjects:
#                subjects = {}
#
    if 'marc_subjects' in w:
        try:
            marc_subjects = eval(w['marc_subjects'])
        except:
            print 'error parsing marc subjects (%d)' % len(w['marc_subjects'])
            marc_subjects = []
        try:
            subjects = find_subjects(marc_subjects)
        except ValueError:
            print w['marc_subjects']
            raise

        subjects = four_types(subjects)

        for k in 'person', 'place', 'subject', 'time':
            if k not in subjects:
                continue
            add_field_list(doc, k, subjects[k].keys())
            #add_field_list(doc, k + '_facet', subjects[k].keys())
            subject_keys = [str_to_key(s) for s in subjects[k].keys()]
            add_field_list(doc, k + '_key', subject_keys)

    return doc

def all_works():
    for line in open('work_full3'):
        yield line
    for line in open('work_full4'):
        yield line

def index():
    t0 = time()
    t_prev = time()
    total = 13941626
    num = 0
    add = Element("add")
    chunk = 500
    chunk_count = 0
    print 'reading works'
    # 9260000
    # OL9177682W, OL9177683W, OL9177684W, OL9177685W, OL9177686W, OL9177687W, OL9177688W, OL9177689W
    skip = 'OL9177682W' #, OL9177683W, OL9177684W, OL9177685W, OL9177686W, OL9177687W, OL9177688W, OL9177689W
    skip = None
    for line in open('work_full5'):
        num += 1
#        if num < 13600000:
#            if num % 100000 == 0:
#                print num, 'skipping'
#            continue
        if skip and skip not in line:
            continue
        w = eval(line)
        if skip:
            if w['key'] == '/works/' + skip:
                print 'finished skipping'
                skip = None
            else:
                continue
#        for e in w['editions']:
#            pub_date_missing = True
#            if 'publish_date' in e:
#                if all(len(l) == 3 for l in e['publish_date'].split('\t')):
#                    e['languages'] = e['publish_date'].split('\t')
#                    del e['publish_date']
#                else:
#                    pub_date_missing = False
#            if pub_date_missing:
#                pub_dates = list(db.select('pub_dates', what="v", where="k='/b/OL%dM'" % e['ekey']))
#                if pub_dates:
#                    e['publish_date'] = pub_dates[0].v.decode('utf-8')

        doc = build_doc(w)
        if doc is not None:
            add.append(doc)

        if len(add) == chunk:
            chunk_count += 1
            add_xml = tostring(add, pretty_print=True).encode('utf-8')
            #add_xml = tostring(add, pretty_print=True)
            del add # memory
            secs = float(time() - t_prev)
            rec_per_sec = float(chunk) / secs
            rec_left = total - num
            sec_left = rec_left / rec_per_sec
            print "%d/%d %.4f%% %.2f rec/sec %.2f hours left" % (num,total,(float(num)*100.0/total), rec_per_sec, float(sec_left) / 3600.0), solr_post(h1, add_xml)
#            if chunk_count % 10000 == 0:
#                print 'commit:', solr_post(h1, '<commit/>')
            add = Element("add")
            t_prev = time()

    if len(add):
        add_xml = tostring(add, pretty_print=True).encode('utf-8')
        del add # memory
        print solr_post(h1, add_xml),
        print 'commit:', solr_post(h1, '<commit/>')
    print 'optimize'
    print solr_post(h1, '<optimize/>')
    print 'end'

index()
