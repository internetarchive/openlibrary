import web, re, httplib, sys, urllib2
import simplejson as json
import openlibrary.catalog.importer.pool as pool
from openlibrary.catalog.merge.merge_marc import build_marc
from openlibrary.catalog.read_rc import read_rc
from openlibrary.catalog.importer.load import build_query, east_in_by_statement, import_author
from openlibrary.catalog.utils.query import query, withKey
from openlibrary.catalog.importer.merge import try_merge
from openlibrary.catalog.importer.lang import add_lang
from openlibrary.catalog.importer.update import add_source_records
from openlibrary.catalog.get_ia import get_ia, urlopen_keep_trying
from openlibrary.catalog.importer.db_read import get_mc
import openlibrary.catalog.marc.parse_xml as parse_xml
from time import time, sleep
import openlibrary.catalog.marc.fast_parse as fast_parse
sys.path.append('/home/edward/src/olapi')
from olapi import OpenLibrary, unmarshal

rc = read_rc()
ol = OpenLibrary("http://openlibrary.org")
ol.login('ImportBot', rc['ImportBot']) 

db_amazon = web.database(dbn='postgres', db='amazon')
db_amazon.printing = False

db = web.database(dbn='mysql', host=rc['ia_db_host'], user=rc['ia_db_user'], \
        passwd=rc['ia_db_pass'], db='archive')
db.printing = False

iter = db.query("select identifier, updated from metadata where scanner is not null and noindex is null and mediatype='texts' and (curatestate='approved' or curatestate is null) and scandate is not null and updated > '2009-07-14 08:26:16' order by updated")

t0 = time()
t_prev = time()
rec_no = 0
chunk = 50
load_count = 0

def read_short_title(title):
    return str(fast_parse.normalize_str(title)[:25])

def make_index_fields(rec):
    fields = {}
    for k, v in rec.iteritems():
        if k in ('lccn', 'oclc', 'isbn'):
            fields[k] = v
            continue
        if k == 'full_title':
            fields['title'] = [read_short_title(v)]
    return fields

archive_url = "http://archive.org/download/"

def load(loc, ia):
    print "load", loc, ia
    url = archive_url + loc
    f = urlopen_keep_trying(url)
    try:
        edition = parse_xml.parse(f)
    except AssertionError:
        return
    except parse_xml.BadSubtag:
        return
    except KeyError:
        return
    if 'title' not in edition:
        return
    edition['ocaid'] = ia
    write_edition("ia:" + ia, edition)

def write_edition(loc, edition):
    add_lang(edition)
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
    key = ret
    pool.update(key, q)

skip = True
skip = False

for i in iter:
    ia = i.identifier
    if skip:
        if ia == 'documentsrelatin28newjuoft':
            skip = False
        else:
            continue
    print ia, i.updated
    if query({'type': '/type/edition', 'ocaid': ia}):
        print 'already loaded'
        continue
    if query({'type': '/type/edition', 'source_records': 'ia:' + ia}):
        print 'already loaded'
        continue
    try:
        loc, rec = get_ia(ia)
    except (KeyboardInterrupt, NameError):
        raise
    except urllib2.HTTPError:
        continue
    if loc is None or rec is None:
        continue
    print loc, rec

    if not loc.endswith('.xml'):
        print "not XML"
        continue
    if 'full_title' not in rec:
        print "full_title missing"
        continue
    index_fields = make_index_fields(rec)
    if not index_fields:
        print "no index_fields"
        continue

    edition_pool = pool.build(index_fields)

    if not edition_pool:
        load(loc, ia)
        continue

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
                add_source_records(edition_key, ia)
                match = True
                break
        if match:
            break

    if not match:
        load(loc, ia)

print "finished"
