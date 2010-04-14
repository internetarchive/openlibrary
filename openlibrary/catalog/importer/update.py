import re, web, sys
import simplejson as json
from urllib2 import urlopen, URLError
from openlibrary.catalog.read_rc import read_rc
from openlibrary.catalog.importer.db_read import get_mc
from time import sleep
from openlibrary.catalog.title_page_img.load import add_cover_image
from openlibrary.api import OpenLibrary, unmarshal, marshal

rc = read_rc()
ol = OpenLibrary("http://openlibrary.org")
ol.login('ImportBot', rc['ImportBot']) 

db_amazon = web.database(dbn='postgres', db='amazon')
db_amazon.printing = False

re_meta_mrc = re.compile('^([^/]*)_meta.mrc:0:\d+$')

def make_redirect(old, new, msg='replace with redirect'):
    r = {'type': {'key': '/type/redirect'}, 'location': new}
    ol.save(old, r, msg)

def amazon_source_records(asin):
    iter = db_amazon.select('amazon', where='asin = $asin', vars={'asin':asin})
    return ["amazon:%s:%s:%d:%d" % (asin, r.seg, r.start, r.length) for r in iter]

def fix_toc(e):
    toc = e.get('table_of_contents', None)
    if not toc:
        return
    if isinstance(toc[0], dict) and toc[0]['type'] == '/type/toc_item':
        return
    return [{'title': unicode(i), 'type': '/type/toc_item'} for i in toc if i != u'']

re_skip = re.compile('\b([A-Z]|Co|Dr|Jr|Capt|Mr|Mrs|Ms|Prof|Rev|Revd|Hon)\.$')

def has_dot(s):
    return s.endswith('.') and not re_skip.search(s)

def undelete_author(a):
    key = a['key']
    assert a['type'] == '/type/delete'
    url = 'http://openlibrary.org' + key + '.json?v=' + str(a['revision'] - 1)
    prev = unmarshal(json.load(urlopen(url)))
    assert prev['type'] == '/type/author'
    ol.save(key, prev, 'undelete author')

def undelete_authors(authors):
    for a in authors:
        if a['type'] == '/type/delete':
            undelete_author(a)
        else:
            print a
            assert a['type'] == '/type/author'

def add_source_records(key, ia, v=None):
    new = 'ia:' + ia
    sr = None
    e = ol.get(key, v=v)
    need_update = False
    if 'ocaid' not in e:
        need_update = True
        e['ocaid'] = ia
    if 'source_records' in e:
        if new in e['source_records'] and not need_update:
            return
        e['source_records'].append(new)
    else:
        existing = get_mc(key)
        amazon = 'amazon:'
        if existing is None:
            sr = []
        elif existing.startswith('ia:'):
            sr = [existing]
        elif existing.startswith(amazon):
            sr = amazon_source_records(existing[len(amazon):]) or [existing]
        else:
            m = re_meta_mrc.match(existing)
            sr = ['marc:' + existing if not m else 'ia:' + m.group(1)]
        if 'ocaid' in e and 'ia:' + e['ocaid'] not in sr:
            sr.append('ia:' + e['ocaid'])
        if new not in sr:
            e['source_records'] = sr + [new]

    # fix other bits of the record as well
    new_toc = fix_toc(e)
    if new_toc:
        e['table_of_contents'] = new_toc
    if e.get('subjects', None) and any(has_dot(s) for s in e['subjects']):
        subjects = [s[:-1] if has_dot(s) else s for s in e['subjects']]
        e['subjects'] = subjects
    if 'authors' in e:
        assert not any(a=='None' for a in e['authors'])
        print e['authors']
        authors = [ol.get(akey) for akey in e['authors']]
        authors = [ol.get(a['location']) if a['type'] == '/type/redirect' else a \
                for a in authors]
        e['authors'] = [{'key': a['key']} for a in authors]
        undelete_authors(authors)
    print 'saving', key
    print marshal(e)
    print ol.save(key, e, 'found a matching MARC record')
#    for attempt in range(50):
#        try:
#            print ol.save(key, e, 'found a matching MARC record')
#            break
#        except KeyboardInterrupt:
#            raise
#        except URLError:
#            if attempt == 49:
#                raise
#        except:
#            print e
#            raise
#        print 'attempt %d failed' % attempt
#        sleep(30)
    if new_toc:
        new_edition = ol.get(key)
        # [{u'type': <ref: u'/type/toc_item'>}, ...]
        assert 'title' in new_edition['table_of_contents'][0]
    add_cover_image(key, ia)

def ocaid_and_source_records(key, ocaid, source_records):
    e = ol.get(key)
    need_update = False
    e['ocaid'] = ocaid
    e['source_records'] = source_records

    # fix other bits of the record as well
    new_toc = fix_toc(e)
    if new_toc:
        e['table_of_contents'] = new_toc
    if e.get('subjects', None) and any(has_dot(s) for s in e['subjects']):
        subjects = [s[:-1] if has_dot(s) else s for s in e['subjects']]
        e['subjects'] = subjects
    if 'authors' in e:
        assert not any(a=='None' for a in e['authors'])
        print e['authors']
        authors = [ol.get(akey) for akey in e['authors']]
        authors = [ol.get(a['location']) if a['type'] == '/type/redirect' else a \
                for a in authors]
        e['authors'] = [{'key': a['key']} for a in authors]
        undelete_authors(authors)
    try:
        print ol.save(key, e, 'merge scanned books')
    except:
        print e
        raise
    if new_toc:
        new_edition = ol.get(key)
        # [{u'type': <ref: u'/type/toc_item'>}, ...]
        assert 'title' in new_edition['table_of_contents'][0]
