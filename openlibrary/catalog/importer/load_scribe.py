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
from openlibrary.catalog.get_ia import get_ia, urlopen_keep_trying, NoMARCXML
from openlibrary.catalog.importer.db_read import get_mc
from openlibrary.catalog.title_page_img.load import add_cover_image
from openlibrary.solr.update_work import update_work, solr_update
import openlibrary.catalog.marc.parse_xml as parse_xml
from time import time, sleep
import openlibrary.catalog.marc.fast_parse as fast_parse
from openlibrary.api import OpenLibrary, unmarshal

rc = read_rc()
ol = OpenLibrary("http://openlibrary.org")
ol.login('ImportBot', rc['ImportBot']) 

db_amazon = web.database(dbn='postgres', db='amazon')
db_amazon.printing = False

db = web.database(dbn='mysql', host=rc['ia_db_host'], user=rc['ia_db_user'], \
        passwd=rc['ia_db_pass'], db='archive')
db.printing = False

re_census = re.compile('^\d+(st|nd|rd|th)census')

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
    except parse_xml.BadSubtag:
        return
    if 'title' not in edition:
        return
    edition['ocaid'] = ia
    write_edition(ia, edition)

def write_edition(ia, edition):
    loc = 'ia:' + ia
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

    for attempt in range(50):
        if attempt > 0:
            print 'retrying'
        try:
            ret = ol.new(q, comment='initial import')
        except httplib.BadStatusLine:
            sleep(30)
            continue
        except: # httplib.BadStatusLine
            print q
            raise
        break
    print 'ret:', ret
    assert isinstance(ret, basestring)
    key = ret
    pool.update(key, q)

    print 'add_cover_image'
    add_cover_image(key, ia)

fh_log = None

def write_log(ia, when, msg):
    print >> fh_log, (ia, when, msg)
    fh_log.flush()

def hide_books(start):
    mend = []
    fix_works = set()
    db_iter = db.query("select identifier, updated from metadata where (noindex is not null or curatestate='dark') and mediatype='texts' and scandate is not null and updated > $start order by updated", {'start': start})
    for row in db_iter:
        ia = row.identifier
        print `ia`, row.updated
        for eq in query({'type': '/type/edition', 'ocaid': ia}):
            print eq['key']
            e = ol.get(eq['key'])
            if 'ocaid' not in e:
                continue
            if 'works' in e:
                fix_works.update(e['works'])
            print e['key'], `e.get('title', None)`
            del e['ocaid']
            mend.append(e)
    print 'removing links from %d editions' % len(mend)
    print ol.save_many(mend, 'remove link')
    requests = []
    for wkey in fix_works:
        requests += update_work(withKey(wkey))
    if fix_works:
        solr_update(requests + ['<commit/>'], debug=True)

if __name__ == '__main__':
    fh_log = open('/1/edward/logs/load_scribe', 'a')

    state_file = rc['state_dir'] + '/load_scribe'
    start = open(state_file).readline()[:-1]

    while True:
        print 'start:', start

        hide_books(start)

        db_iter = db.query("select identifier, updated from metadata where scanner is not null and noindex is null and mediatype='texts' and (curatestate='approved' or curatestate is null) and scandate is not null and updated > $start order by updated", {'start': start})
        t_start = time()
        for row in db_iter:
            ia = row.identifier
            if re_census.match(ia):
                print 'skip census for now:', ia
                continue
            print `ia`, row.updated
            when = str(row.updated)
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
            except NoMARCXML:
                write_log(ia, when, "no MARCXML")
                continue
            except urllib2.HTTPError as error:
                write_log(ia, when, "error: HTTPError: " + str(error))
                continue
            if loc is None:
                write_log(ia, when, "error: no loc ")
            if rec is None:
                write_log(ia, when, "error: no rec")
                continue
            if 'physical_format' in rec:
                format = rec['physical_format'].lower()
                if format.startswith('[graphic') or format.startswith('[cartograph'):
                    continue
            print loc, rec

            if not loc.endswith('.xml'):
                print "not XML"
                write_log(ia, when, "error: not XML")
                continue
            if 'full_title' not in rec:
                print "full_title missing"
                write_log(ia, when, "error: full_title missing")
                continue
            index_fields = make_index_fields(rec)
            if not index_fields:
                print "no index_fields"
                write_log(ia, when, "error: no index fields")
                continue

            edition_pool = pool.build(index_fields)

            if not edition_pool:
                load(loc, ia)
                write_log(ia, when, "loaded")
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
                        write_log(ia, when, "found match: " + edition_key)
                        match = True
                        break
                if match:
                    break

            if not match:
                load(loc, ia)
                write_log(ia, when, "loaded")
        start = row.updated
        secs = time() - t_start
        mins = secs / 60
        print "finished %d took mins" % mins
        print >> open(state_file, 'w'), start
        if mins < 30:
            print 'waiting'
            sleep(60 * 30 - secs)
