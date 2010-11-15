import re, web
from openlibrary.catalog.importer.db_read import get_mc
from openlibrary.api import unmarshal
from time import sleep

re_meta_mrc = re.compile('([^/]+)_(meta|marc).(mrc|xml)')
re_skip = re.compile('\b([A-Z]|Co|Dr|Jr|Capt|Mr|Mrs|Ms|Prof|Rev|Revd|Hon)\.$')

db_amazon = web.database(dbn='postgres', db='amazon')
db_amazon.printing = False

def query_with_retry(ol, q):
    for attempt in range(50):
        try:
            return ol.query(q)
        except:
            sleep(5)
            print 'retry attempt', attempt

def get_with_retry(ol, k):
    for attempt in range(50):
        try:
            return ol.get(k)
        except:
            sleep(5)
            print 'retry attempt', attempt

def amazon_source_records(asin):
    iter = db_amazon.select('amazon', where='asin = $asin', vars={'asin':asin})
    return ["amazon:%s:%s:%d:%d" % (asin, r.seg, r.start, r.length) for r in iter]

def has_dot(s):
    return s.endswith('.') and not re_skip.search(s)

def fix_toc(e):
    toc = e.get('table_of_contents', None)
    if not toc:
        return
    if isinstance(toc[0], dict) and toc[0]['type'] == '/type/toc_item':
        if len(toc) == 1 and 'title' not in toc[0]:
            del e['table_of_contents'] # remove empty toc
        return
    new_toc = [{'title': unicode(i), 'type': '/type/toc_item'} for i in toc if i != u'']
    e['table_of_contents'] = new_toc

def fix_subject(e):
    if e.get('subjects', None) and any(has_dot(s) for s in e['subjects']):
        subjects = [s[:-1] if has_dot(s) else s for s in e['subjects']]
        e['subjects'] = subjects

def undelete_author(a, ol):
    key = a['key']
    assert a['type'] == '/type/delete'
    url = 'http://openlibrary.org' + key + '.json?v=' + str(a['revision'] - 1)
    prev = unmarshal(json.load(urllib2.urlopen(url)))
    assert prev['type'] == '/type/author'
    ol.save(key, prev, 'undelete author')

def undelete_authors(authors, ol):
    for a in authors:
        if a['type'] == '/type/delete':
            undelete_author(a, ol)
        else:
            assert a['type'] == '/type/author'

def fix_authors(e, ol):
    if 'authors' not in e:
        return
    authors = [get_with_retry(ol, akey) for akey in e['authors']]
    while any(a['type'] == '/type/redirect' for a in authors):
        print 'following redirects'
        authors = [get_with_retry(ol, a['location']) if a['type'] == '/type/redirect' else a for a in authors]
    e['authors'] = [{'key': a['key']} for a in authors]
    undelete_authors(authors, ol)

def fix_edition(key, e, ol):
    existing = get_mc(key)
    if 'source_records' not in e and existing:
        amazon = 'amazon:'
        if existing.startswith('ia:'):
            sr = [existing]
        elif existing.startswith(amazon):
            sr = amazon_source_records(existing[len(amazon):]) or [existing]
        else:
            print 'existing:', existing
            m = re_meta_mrc.search(existing)
            sr = ['marc:' + existing if not m else 'ia:' + m.group(1)]
        e['source_records'] = sr
    if 'ocaid' in e:
        ia = 'ia:' + e['ocaid']
        if 'source_records' not in e:
            e['source_records'] = [ia]
        elif ia not in e['source_records']:
            e['source_records'].append(ia)

    fix_toc(e)
    fix_subject(e)
    fix_authors(e, ol)
    return e
