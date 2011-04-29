#!/usr/bin/python2.5
from time import time, sleep
import catalog.marc.fast_parse as fast_parse
import web, sys, codecs, re
import catalog.importer.pool as pool
from catalog.utils.query import query_iter
from catalog.importer.merge import try_merge
from catalog.marc.new_parser import read_edition
from catalog.importer.load import build_query
from catalog.get_ia import files, read_marc_file
from catalog.merge.merge_marc import build_marc
from catalog.importer.db_read import get_mc, withKey
from openlibrary.api import OpenLibrary

from catalog.read_rc import read_rc

rc = read_rc()

marc_index = web.database(dbn='postgres', db='marc_index')
marc_index.printing = False

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
    toc = e.get('table_of_contents')
    if not toc:
        return
    if isinstance(toc[0], dict) and toc[0]['type'] == '/type/toc_item':
        return
    return [{'title': unicode(i), 'type': '/type/toc_item'} for i in toc if i != u'']

re_skip = re.compile('\b([A-Z]|Co|Dr|Jr|Capt|Mr|Mrs|Ms|Prof|Rev|Revd|Hon)\.$')

def has_dot(s):
    return s.endswith('.') and not re_skip.search(s)

def add_source_records(key, new, thing):
    sr = None
    e = ol.get(key)
    if 'source_records' in e:
        if new in e['source_records']:
            return
        e['source_records'].append(new)
    else:
        existing = get_mc(key)
        amazon = 'amazon:'
        if existing.startswith(amazon):
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
    print ol.save(key, e, 'found a matching MARC record')
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
        if not index_fields or 'title' not in index_fields:
            continue

        edition_pool = pool.build(index_fields)

        if not edition_pool:
            continue

        rec = fast_parse.read_edition(data)
        e1 = build_marc(rec)

        match = False
        seen = set()
        for k, v in edition_pool.iteritems():
            for edition_key in v:
                if edition_key in seen:
                    continue
                seen.add(edition_key)
                thing = withKey(edition_key)
                assert thing
                if try_merge(e1, edition_key, thing):
                    add_source_records(edition_key, loc, thing)
                    match = True

        if not match:
            yield loc, data

start = pool.get_start(archive_id)
go = 'part' not in start

print archive_id

for part, size in files(archive_id):
    print part, size
    load_part(archive_id, part)

print "finished"
