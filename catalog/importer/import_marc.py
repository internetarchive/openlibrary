#!/usr/bin/python2.5
from time import time, sleep
import catalog.marc.fast_parse as fast_parse
import web, sys, codecs
import catalog.importer.pool as pool
from catalog.importer.merge import try_merge
from catalog.importer.new_parser import read_edition
from catalog.importer.load import build_query
from catalog.olwrite import Infogami, add_to_database
from catalog.importer.lang import add_lang
from catalog.get_ia import files, read_marc_file
from catalog.merge.merge_marc import build_marc
from catalog.importer.db_read import get_versions

from catalog.read_rc import read_rc

rc = read_rc()
infogami = Infogami(rc['infogami'])
infogami.login('ImportBot', rc['ImportBot']

marc_path = '/2/pharos/marc/'

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

t0 = time()
t_prev = time()
rec_no = 0
chunk = 50
last_key = None
load_count = 0

archive_url = "http://archive.org/download/"

archive_id = sys.argv[1]

def percent(a, b):
    return float(a * 100.0) / b

def load_part(archive_id, part, start_pos=0):
    global rec_no, t_prev, last_key, load_count
    t_pool = 0
    t_match = 0
    t_existing = 0
    full_part = archive_id + "/" + part
    f = open(marc_path + full_part)
    if start_pos:
        f.seek(start_pos)
    for pos, loc, data in read_marc_file(full_part, f, pos=start_pos):
        rec_no += 1
        if rec_no % chunk == 0:
            cur_time = time()
            t = cur_time - t_prev
            t_prev = cur_time
            t1 = cur_time - t0
            rec_per_sec = chunk / t
            bytes_per_sec_total = (pos - start_pos) / t1

            q = {
                'cur': loc,
                'chunk': chunk,
                'rec_no': rec_no,
                't': t,
                't1': t1,
                't_pool': t_pool,
                't_match': t_match,
                'part': part,
                'pos': pos,
                'last_key': last_key,
                'load_count': load_count,
                'time': cur_time,
                'bytes_per_sec_total': bytes_per_sec_total,
            }
            pool.post_progress(archive_id, q)
            t_pool = 0
            t_match = 0
            t_existing = 0

        v = get_versions({'machine_comment': loc})
        if v:
            continue
        try:
            index_fields = fast_parse.index_fields(data, ['010', '020', '035', '245'])
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
            yield loc, data
            continue

        rec = fast_parse.read_edition(data)
        e1 = build_marc(rec)

        match = False
        for k, v in edition_pool.iteritems():
            for edition_key in v:
                if try_merge(e1, edition_key.replace('\/', '/')):
                    match = True
                    break
            if match:
                break

        if not match:
            yield loc, data

start = pool.get_start(archive_id)
go = 'part' not in start

print archive_id

def new_key(type):
    for i in range(50):
        try:
            return infogami.new_key(type)
        except (KeyboardInterrupt, NameError):
            raise
        except:
            pass
        sleep(30)
    return infogami.new_key(type)

def write(q, loc):
    for i in range(50):
        continue
        try:
            return infogami.write(q, comment='initial import', machine_comment=loc)
        except (KeyboardInterrupt, NameError):
            raise
        except:
            pass
        sleep(30)
    try:
        return infogami.write(q, comment='initial import', machine_comment=loc)
    except:
        print q
        raise

def write_edition(loc, edition):
    add_lang(edition)
    q = build_query(loc, edition)

    for a in (i for i in q.get('authors', []) if 'key' not in i):
        a['key'] = new_key('/type/author')

    key = new_key('/type/edition')
    q['key'] = key
    ret = write(q, loc)
    assert ret['status'] == 'ok'
    pool.update(key, q)

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
        if loc == 'marc_binghamton_univ/bgm_openlib_final_10-15.mrc:265680068:4538':
            continue
        try:
            edition = read_edition(loc, data)
        except AssertionError:
            print loc
            raise
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

print "finished"
