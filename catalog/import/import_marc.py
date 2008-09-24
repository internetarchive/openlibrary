#!/usr/bin/python2.5
import xml.parsers.expat
from time import time
import catalog.marc.fast_parse as fast_parse
from catalog.merge.merge_marc import *
import catalog.merge.amazon as amazon
from catalog.get_ia import *
from pprint import pprint
import web, sys, codecs, psycopg2, cjson
from parse import read_edition
from load import build_query
from urllib2 import urlopen, Request
import urllib2

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

amazon.set_isbn_match(225)

web.config.db_parameters = dict(dbn='postgres', db='', user='', pw='', host='pharosdb.us.archive.org')
web.load()
web.ctx.ip = '127.0.0.1'
threshold = 875

t0 = time()
t_prev = time()
rec_no = 0
chunk = 50
last_key = None
load_count = 0

pool_url = 'http://wiki-beta.us.archive.org:9020/'

from infogami.infobase.infobase import Infobase, NotFound
import infogami.infobase.writequery as writequery
site = Infobase().get_site('openlibrary.org')

# login as ImportBot
site.get_account_manager().set_auth_token(site.withKey('/user/ImportBot'))

archive_url = "http://archive.org/download/"

archive_id = sys.argv[1]

def get_mc(id):
    versions = site.versions({ 'thing_id': id })
    comments = [i['machine_comment'] for i in versions if 'machine_comment' in i and i['machine_comment'] is not None ]
    if len(comments) == 0:
        return None
    if len(comments) != 1:
        print id
        print versions
    assert len(comments) == 1
    return comments[0]

def build_pool(fields):
    params = dict((k, '_'.join(v)) for k, v in fields.iteritems() if k != 'author')
    url = pool_url + "?" + web.http.urlencode(params)
    ret = cjson.decode(urlopen(url).read())
    return ret['pool']

def try_amazon(thing):
    data = thing._get_data()
    if 'isbn_10' not in data:
        return None
    if 'authors' in data:
        authors = [a.name.value for a in thing.authors if a.name.value]
    else:
        authors = []
    return amazon.build_amazon(thing._get_data(), authors)

def try_merge(e1, doc_id):
    try:
        thing = site.withID(doc_id)
    except NotFound:
        print doc_id
        print e1
        raise
    ia = None
    thing_type = str(thing.type)
    if thing_type == '/type/delete': # 
        return False
    if thing_type != '/type/edition':
        print thing_type
    assert thing_type == '/type/edition'
    try:
        ia = thing.ocaid.value
    except AttributeError:
        pass
    rec2 = None
    if ia:
        try:
            loc2, rec2 = get_ia(ia)
        except xml.parsers.expat.ExpatError:
            return False
        except urllib2.HTTPError, error:
            assert error.code == 404
    if not rec2:
        mc = get_mc(doc_id)
        if not mc:
            return False
        if mc.startswith('amazon:'):
            try:
                a = try_amazon(thing)
            except IndexError:
                print thing.key
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
                print thing.key
                raise
        try:
            rec2 = fast_parse.read_edition(get_from_archive(mc))
        except (fast_parse.SoundRecording, IndexError, AssertionError):
            print mc
            print thing.key
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
    global rec_no, t_prev, last_key, load_count
    t_pool = 0
    t_match = 0
    t_existing = 0
    full_part = archive_id + "/" + part
    url = archive_url + full_part
    if start_pos:
        req = urllib2.Request(url, None, {'Range':'bytes=%d-'% start_pos},)
        f = urlopen_keep_trying(req)
    else:
        f = urlopen_keep_trying(url)
    for pos, loc, data in read_marc_file(full_part, f, pos=start_pos):
        rec_no += 1
        if rec_no % chunk == 0:

            cur_time = time()
            t = cur_time - t_prev
            t_prev = cur_time
            t1 = cur_time - t0
            rec_per_sec = chunk / t
#            rec_per_sec_total = rec_no / t1
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

        v = site.versions({'machine_comment': loc})
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
        try:
            for k, v in pool.iteritems():
                for doc_id in v:
                    if try_merge(e1, doc_id):
                        match = True
                        break
                if match:
                    break
        except NotFound:
            continue
        t_match += time() - t_start
#        print match

        if not match:
            yield loc, data

def write_to_database(q, loc):
    q['loc'] = loc
    req = Request(pool_url, cjson.encode(q))
    for i in range(5):
        try:
            return urlopen(req).read().strip()
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
            except (AssertionError, IndexError, ValueError, KeyError):
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
            q = build_query(loc, edition)
            last_key = write_to_database(q, loc)
    except AssertionError:
        raise

print "finished"
