#!/usr/bin/python2.5
import xml.parsers.expat
from time import time, sleep
import catalog.marc.fast_parse as fast_parse
from catalog.merge.merge_marc import *
import catalog.merge.amazon as amazon
from catalog.get_ia import *
from pprint import pprint
import web, sys, codecs, cjson, urllib2, dbhash
from parse import read_edition
from load_web import build_query, get_versions, withKey
from urllib2 import urlopen, Request
from olwrite import Infogami, add_to_database

api_versions = "http://openlibrary.org/api/versions?"
api_things = "http://openlibrary.org/api/things?"

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

amazon.set_isbn_match(225)
reached_checkpoint = False

index_path = '/1/pharos/edward/index/2/'
key_to_mc = dbhash.open(index_path + "key_to_mc.dbm", flag='r')

marc_path = '/2/pharos/marc/'

def get_things(q):
    url = api_things + web.http.urlencode({'query': cjson.encode(q)})
    data = urlopen(url).read()
    ret = cjson.decode(data)
    assert ret['status'] == 'ok'
    return [i.replace('\/', '/') for i in ret['result']]

def get_data(loc):
    try:
        filename, p, l = loc.split(':')
    except ValueError:
        return None
    if not os.path.exists(marc_path + filename):
        return None
    f = open(marc_path + filename)
    f.seek(int(p))
    buf = f.read(int(l))
    f.close()
    return buf

threshold = 875

t0 = time()
t_prev = time()
rec_no = 0
chunk = 50
last_key = None
load_count = 0

pool_url = 'http://wiki-beta.us.archive.org:9020/'

lang = []
offset = 0
while True:
    i = get_things({'type': '/type/language', 'limit': 100, 'offset': offset})
    lang += i
    if len(i) != 100:
        break
    offset += 100

languages = set(lang)

archive_url = "http://archive.org/download/"

archive_id = sys.argv[1]

def get_mc(edition_key):
    versions = get_versions({ 'key': edition_key })
    comments = [i['machine_comment'] for i in versions if 'machine_comment' in i and i['machine_comment'] is not None ]
    if len(comments) == 0:
        return None
    if len(comments) != 1:
        print id
        print versions
    assert len(comments) == 1
    if comments[0] == 'initial import':
        return None
    return comments[0]

def build_pool(fields):
    params = dict((k, '_'.join(v)) for k, v in fields.iteritems() if k != 'author')
    url = pool_url + "?" + web.http.urlencode(params)
    ret = cjson.decode(urlopen(url).read())
    return ret['pool']

def try_amazon(thing):
    if 'isbn_10' not in thing:
        return None
    if 'authors' in thing:
        authors = []
        for a in thing['authors']:
            author_thing = withKey(a['key'])
            if 'name' in author_thing:
                authors.append(author_thing['name'])
    else:
        authors = []
    return amazon.build_amazon(thing, authors)

def try_merge(e1, edition_key):
    ia = None
    mc = None
    if edition_key in key_to_mc:
        mc = key_to_mc[edition_key]
        if mc.startswith('ia:'):
            ia = mc[3:]
        elif mc.endswith('.xml') or mc.endswith('.mrc'):
            ia = mc[:mc.find('/')]
    if not mc or mc.startswith('amazon:'):
        thing = withKey(edition_key)
        thing_type = thing['type']['key']
        if thing_type == '/type/delete': # 
            return False
        assert thing_type == '/type/edition'

    rec2 = None
    if ia:
        try:
            loc2, rec2 = get_ia(ia)
        except xml.parsers.expat.ExpatError:
            return False
        except urllib2.HTTPError, error:
            assert error.code == 404
        if not rec2:
            return True
    if not rec2:
        if not mc:
            mc = get_mc(thing['key'])
        if not mc:
            return False
        if mc.startswith('amazon:'):
            try:
                a = try_amazon(thing)
            except IndexError:
                print thing['key']
                raise
            except AttributeError:
                return False
            if not a:
                return False
            try:
                return amazon.attempt_merge(a, e1, threshold, debug=False)
            except:
                print a
                print e1
                print thing['key']
                raise
        try:
            data = get_data(mc)
            if not data:
                return True
            rec2 = fast_parse.read_edition(data)
        except (fast_parse.SoundRecording, IndexError, AssertionError):
            print mc
            print thing['key']
            raise
    if not rec2:
        return False
    try:
        e2 = build_marc(rec2)
    except TypeError:
        print rec2
        raise
    return attempt_merge(e1, e2, threshold, debug=False)

def percent(a, b):
    return float(a * 100.0) / b

def post_progress(archive_id, q):
    url = pool_url + "store/" + archive_id
    req = Request(url, cjson.encode(q))
    urlopen(req).read()

def load_part(archive_id, part, start_pos=0):
    global rec_no, t_prev, last_key, load_count, reached_checkpoint
    t_pool = 0
    t_match = 0
    t_existing = 0
    full_part = archive_id + "/" + part
    if start_pos:
        f = open(marc_path + full_part)
        f.seek(start_pos)
    else:
        f = open(marc_path + full_part)
    for pos, loc, data in read_marc_file(full_part, f, pos=start_pos):
        rec_no += 1
        if rec_no % chunk == 0:
            reached_checkpoint = True

            cur_time = time()
            t = cur_time - t_prev
            t_prev = cur_time
            t1 = cur_time - t0
            rec_per_sec = chunk / t
#            rec_per_sec_total = rec_no / t1
            bytes_per_sec_total = (pos - start_pos) / t1
#            remaining = total - rec_no
#            sec = remaining / rec_per_sec_total

            q = {
                'cur': loc,
                'chunk': chunk,
                'rec_no': rec_no,
                't': t,
                't1': t1,
#                'remaining': remaining,
                't_pool': t_pool,
                't_match': t_match,
                'part': part,
                'pos': pos,
                'last_key': last_key,
                'load_count': load_count,
                'time': cur_time,
                'bytes_per_sec_total': bytes_per_sec_total,
            }
            post_progress(archive_id, q)
#            print archive_id
#            print "%8d current: %9.3f overall: %9.3f" % (rec_no, rec_per_sec, rec_per_sec_total),
#            hours = sec / 3600
#            print "%6.3f hours" % hours
#            print "time spent:",
#            print "%.2f%% building pool" % percent(t_pool, t),
#            print "%.2f%% checking for matches" % percent(t_match, t)
            t_pool = 0
            t_match = 0
            t_existing = 0

        if not reached_checkpoint:
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
        if not index_fields:
            continue

        t_start = time()
        pool = build_pool(index_fields)
        t_pool += time() - t_start

        if not pool:
            yield loc, data
            continue

        if pool.keys() != ['title']:
            continue

        if 'title' in pool and len(pool['title']) > 20:
            continue

        rec = fast_parse.read_edition(data)
        e1 = build_marc(rec)

        t_start = time()
        match = False
#        print pool,
        for k, v in pool.iteritems():
            for edition_key in v:
                if try_merge(e1, edition_key):
                    match = True
                    break
            if match:
                break
        t_match += time() - t_start

        if not match:
            yield loc, data

def write_to_database(infogami, q, loc):
    key = add_to_database(infogami, q, loc)
    q['key'] = key
    req = Request(pool_url, cjson.encode(q))
    urlopen(req).read()
    return key

    for i in range(5):
        try:
            urlopen(req).read()
            return key
        except KeyboardInterrupt:
            raise
        except:
            print 'error writing to database'
            print q
            sleep(5)
            if i == 4:
                raise

start = cjson.decode(urllib2.urlopen(pool_url + "store/" + archive_id).read())
go = 'part' not in start

print archive_id
for part, size in files(archive_id):
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
    try:
        for loc, data in part_iter:
            try:
                edition = read_edition(loc, data)
            except AssertionError:
                print 'AssertionError'
                print loc
                continue
            except (IndexError, ValueError, KeyError):
                print loc
                raise
            if 'title' not in edition:
                print 'title not in edition'
                print loc
                print edition
                raise
            if 'table_of_contents' in edition:
                if isinstance(edition['table_of_contents'][0], list):
                    print loc
                assert not isinstance(edition['table_of_contents'][0], list)
            load_count += 1
            if load_count % 100 == 0:
                print "load count", load_count
            if 'languages' in edition:
                lang_key = edition['languages'][0]['key']
                if lang_key in ('/l/   ', '/l/|||'):
                    del edition['languages']
                elif lang_key not in languages:
                    print lang_key, "not found for", loc
                    del edition['languages']
            q = build_query(loc, edition)
            last_key = write_to_database(infogami, q, loc)
    except AssertionError:
        raise

print "finished"
key_to_mc.close()
