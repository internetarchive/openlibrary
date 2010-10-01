#!/usr/bin/python2.5
from time import time, sleep
import openlibrary.catalog.marc.fast_parse as fast_parse
import web, sys, codecs, re, urllib2, httplib
from openlibrary.catalog.importer import pool
import simplejson as json
from openlibrary.catalog.utils.query import query_iter
from openlibrary.catalog.importer.merge import try_merge
from openlibrary.catalog.marc.parse import read_edition
from openlibrary.catalog.importer.load import build_query, east_in_by_statement, import_author
from openlibrary.catalog.works.find_works import find_title_redirects, find_works, get_books, books_query, update_works
from openlibrary.catalog.get_ia import files, read_marc_file
from openlibrary.catalog.merge.merge_marc import build_marc
from openlibrary.catalog.importer.db_read import get_mc, withKey
from openlibrary.api import OpenLibrary, unmarshal

from openlibrary.catalog.read_rc import read_rc

rc = read_rc()

marc_index = web.database(dbn='postgres', db='marc_index')
marc_index.printing = True

db_amazon = web.database(dbn='postgres', db='amazon')
db_amazon.printing = False

ol = OpenLibrary("http://openlibrary.org")
ol.login('ImportBot', rc['ImportBot']) 

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

t0 = time()
t_prev = time()
rec_no = 0
chunk = 50
load_count = 0

archive_id = sys.argv[1]

def get_with_retry(key):
    for i in range(3):
        try:
            return ol.get(key)
        except urllib2.HTTPError, error:
            if error.code != 500:
                raise
        print 'retry save'
        sleep(10)
    return ol.get(key)

def save_with_retry(key, data, comment):
    for i in range(3):
        try:
            return ol.save(key, data, comment)
        except urllib2.HTTPError, error:
            if error.code != 500:
                raise
        print 'retry save'
        sleep(10)

# urllib2.HTTPError: HTTP Error 500: Internal Server Error

def percent(a, b):
    return float(a * 100.0) / b

def progress(archive_id, rec_no, start_pos, pos):
    global t_prev, load_count
    cur_time = time()
    t = cur_time - t_prev
    t_prev = cur_time
    t1 = cur_time - t0
    rec_per_sec = chunk / t
    bytes_per_sec_total = (pos - start_pos) / t1

    q = {
        'chunk': chunk,
        'rec_no': rec_no,
        't': t,
        't1': t1,
        'part': part,
        'pos': pos,
        'load_count': load_count,
        'time': cur_time,
        'bytes_per_sec_total': bytes_per_sec_total,
    }
    pool.post_progress(archive_id, q)

def is_loaded(loc):
    assert loc.startswith('marc:')
    vars = {'loc': loc[5:]}
    db_iter = marc_index.query('select * from machine_comment where v=$loc', vars)
    if list(db_iter):
        return True
    iter = query_iter({'type': '/type/edition', 'source_records': loc})
    return bool(list(iter))

re_meta_mrc = re.compile('^([^/]*)_meta.mrc:0:\d+$')

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

def author_from_data(loc, data):
    edition = read_edition(data)
    assert 'authors' in edition
    east = east_in_by_statement(edition)
    assert len(edition['authors']) == 1
    print `edition['authors'][0]`
    a = import_author(edition['authors'][0], eastern=east)
    if 'key' in a:
        return {'key': a['key']}
    ret = ol.new(a, comment='new author')
    print 'ret:', ret
    assert isinstance(ret, basestring)
    return {'key': ret}

def undelete_author(a):
    key = a['key']
    assert a['type'] == '/type/delete'
    url = 'http://openlibrary.org' + key + '.json?v=' + str(a['revision'] - 1)
    prev = unmarshal(json.load(urllib2.urlopen(url)))
    assert prev['type'] == '/type/author'
    save_with_retry(key, prev, 'undelete author')

def undelete_authors(authors):
    for a in authors:
        if a['type'] == '/type/delete':
            undelete_author(a)
        else:
            print a
            assert a['type'] == '/type/author'

def add_source_records(key, new, thing, data):
    sr = None
    e = get_with_retry(key)
    if 'source_records' in e:
        if new in e['source_records']:
            return
        e['source_records'].append(new)
    else:
        existing = get_mc(key)
        amazon = 'amazon:'
        if existing.startswith('ia:'):
            sr = [existing]
        elif existing.startswith(amazon):
            sr = amazon_source_records(existing[len(amazon):]) or [existing]
        else:
            m = re_meta_mrc.match(existing)
            sr = ['marc:' + existing if not m else 'ia:' + m.group(1)]
        assert new not in sr
        e['source_records'] = sr + [new]

    # fix other bits of the record as well
    new_toc = fix_toc(e)
    if new_toc:
        e['table_of_contents'] = new_toc
    if e.get('subjects', None) and any(has_dot(s) for s in e['subjects']):
        subjects = [s[:-1] if has_dot(s) else s for s in e['subjects']]
        e['subjects'] = subjects
    if 'authors' in e:
        if any(a=='None' for a in e['authors']):
            assert len(e['authors']) == 1
            new_author = author_from_data(new, data)
            e['authors'] = [new_author]
        else:
            print e['authors']
            authors = [get_with_retry(akey) for akey in e['authors']]
            while any(a['type'] == '/type/redirect' for a in authors):
                print 'following redirects'
                authors = [ol.get(a['location']) if a['type'] == '/type/redirect' else a for a in authors]
            e['authors'] = [{'key': a['key']} for a in authors]
            undelete_authors(authors)
    try:
        print save_with_retry(key, e, 'found a matching MARC record')
    except:
        print e
        raise
    if new_toc:
        new_edition = ol.get(key)
        # [{u'type': <ref: u'/type/toc_item'>}, ...]
        assert 'title' in new_edition['table_of_contents'][0]

def load_part(archive_id, part, start_pos=0):
    print 'load_part:', archive_id, part
    global rec_no, t_prev, load_count
    full_part = archive_id + "/" + part
    f = open(rc['marc_path'] + "/" + full_part)
    if start_pos:
        f.seek(start_pos)
    for pos, loc, data in read_marc_file(full_part, f, pos=start_pos):
        rec_no += 1
        if rec_no % chunk == 0:
            progress(archive_id, rec_no, start_pos, pos)

        if is_loaded(loc):
            continue
        want = ['001', '003', '010', '020', '035', '245']
        try:
            index_fields = fast_parse.index_fields(data, want)
        except KeyError:
            print loc
            print fast_parse.get_tag_lines(data, ['245'])
            raise
        except AssertionError:
            print loc
            raise
        except fast_parse.NotBook:
            continue
        if not index_fields or 'title' not in index_fields:
            continue

        print loc
        edition_pool = pool.build(index_fields)

        if not edition_pool:
            yield loc, data
            continue

        rec = fast_parse.read_edition(data)
        e1 = build_marc(rec)

        match = False
        seen = set()
        for k, v in edition_pool.iteritems():
            for edition_key in v:
                if edition_key in seen:
                    continue
                thing = None
                while not thing or thing['type']['key'] == '/type/redirect':
                    seen.add(edition_key)
                    thing = withKey(edition_key)
                    assert thing
                    if thing['type']['key'] == '/type/redirect':
                        print 'following redirect %s => %s' % (edition_key, thing['location'])
                        edition_key = thing['location']
                if try_merge(e1, edition_key, thing):
                    add_source_records(edition_key, loc, thing, data)
                    match = True
                    break
            if match:
                break

        if not match:
            yield loc, data

start = pool.get_start(archive_id)
go = 'part' not in start

print archive_id

def write(q): # unused
    if 0:
        for i in range(10):
            try:
                return ol.new(q, comment='initial import')
            except (KeyboardInterrupt, NameError):
                raise
            except:
                pass
            sleep(30)
    try:
        return ol.new(q, comment='initial import')
    except:
        print q
        raise

def write_edition(loc, edition):
    q = build_query(loc, edition)
    authors = []
    for a in q.get('authors', []):
        if 'key' in a:
            authors.append({'key': a['key']})
        else:
            try:
                ret = ol.new(a, comment='new author')
            except:
                print a
                raise
            print 'ret:', ret
            assert isinstance(ret, basestring)
#            assert ret['status'] == 'ok'
#            assert 'created' in ret and len(ret['created']) == 1
            authors.append({'key': ret})
    q['source_records'] = [loc]
    if authors:
        q['authors'] = authors

    for attempt in range(5):
        if attempt > 0:
            print 'retrying'
        try:
            ret = ol.new(q, comment='initial import')
        except httplib.BadStatusLine:
            sleep(10)
            continue
        except: # httplib.BadStatusLine
            print q
            raise
        break
    print 'ret:', ret
    assert isinstance(ret, basestring)
#    assert ret['status'] == 'ok'
#    assert 'created' in ret
#    editions = [i for i in ret['created'] if i.startswith('/b/OL')]
#    assert len(editions) == 1
    key = ret
    # get key from return
    pool.update(key, q)

    for a in authors:
        akey = a['key']
        title_redirects = find_title_redirects(akey)
        works = find_works(akey, get_books(akey, books_query(akey)), existing=title_redirects)
        works = list(works)
        updated = update_works(akey, works, do_updates=True)

for part, size in files(archive_id):
#for part, size in marc_loc_updates:
    print part, size
    if not go:
        if part == start['part']:
            go = True
            print "starting %s at %d" % (part, start['pos'])
            part_iter = load_part(archive_id, part, start_pos=start['pos'])
        else:
            continue
    else:
        part_iter = load_part(archive_id, part)

    for loc, data in part_iter:
        #if loc == 'marc_binghamton_univ/bgm_openlib_final_10-15.mrc:265680068:4538':
        #    continue
        edition = read_edition(data)
        if edition['title'] == 'See.':
            print 'See.', edition
            continue
        if edition['title'] == 'See also.':
            print 'See also.', edition
            continue
        load_count += 1
        if load_count % 100 == 0:
            print "load count", load_count
        write_edition(loc, edition)
        sleep(2)

print "finished"
