import MySQLdb
from catalog.read_rc import read_rc
import catalog.marc.fast_parse as fast_parse
import catalog.marc.parse_xml as parse_xml
from time import time
from lang import add_lang
from olwrite import Infogami
from load import build_query
from merge import try_merge
from db_read import get_things
from catalog.get_ia import get_ia, urlopen_keep_trying
from catalog.merge.merge_marc import build_marc
import pool, sys, urllib2

archive_url = "http://archive.org/download/"

rc = read_rc()

infogami = Infogami('pharosdb.us.archive.org:7070')
infogami.login('ImportBot', rc['ImportBot'])

conn = MySQLdb.connect(host=rc['ia_db_host'], user=rc['ia_db_user'], \
        passwd=rc['ia_db_pass'], db='archive')
cur = conn.cursor()

#collection = sys.argv[1]

#print 'loading from collection: %s' % collection

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

def write_edition(loc, edition):
    add_lang(edition)
    q = build_query(loc, edition)

    for a in (i for i in q.get('authors', []) if 'key' not in i):
        a['key'] = infogami.new_key('/type/author')

    key = infogami.new_key('/type/edition')
    last_key = key
    q['key'] = key
    ret = infogami.write(q, comment='initial import', machine_comment=loc)
    assert ret['status'] == 'ok'
    print ret
    pool.update(key, q)

def load():
    global rec_no, t_prev
    skipping = False
    #for ia in ['nybc200715']:
    #cur.execute("select identifier from metadata where collection=%(c)s", {'c': collection})
    cur.execute("select identifier from metadata where scanner is not null and scanner != 'google' and noindex is null and mediatype='texts' and curatestate='approved'") # order by curatedate")
    for ia, in cur.fetchall():
        rec_no += 1
        if rec_no % chunk == 0:
            t = time() - t_prev
            t_prev = time()
            t1 = time() - t0
            rec_per_sec = chunk / t
            rec_per_sec_total = rec_no / t1
            remaining = total - rec_no
            sec = remaining / rec_per_sec_total
            print "%8d current: %9.3f overall: %9.3f" % (rec_no, rec_per_sec, rec_per_sec_total),
            hours = sec / 3600
            print "%6.3f hours" % hours

        print ia
        if get_things({'type': '/type/edition', 'ocaid': ia}):
            print 'already loaded'
            continue
        try:
            loc, rec = get_ia(ia)
        except (KeyboardInterrupt, NameError):
            raise
        except urllib2.HTTPError:
            continue
        if loc is None:
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
        print edition_pool

        if not edition_pool:
            yield loc, ia
            continue

        e1 = build_marc(rec)

        match = False
        for k, v in edition_pool.iteritems():
            if k == 'title' and len(v) > 50:
                continue
            for edition_key in v:
                if try_merge(e1, edition_key.replace('\/', '/')):
                    match = True
                    break
            if match:
                break
        if not match:
            yield loc, ia

t0 = time()
t_prev = time()
chunk = 50
last_key = None
load_count = 0
rec_no = 0
total = 100000

for loc, ia in load():
    print "load", loc, ia
    url = archive_url + loc
    f = urlopen_keep_trying(url)
    try:
        edition = parse_xml.parse(f)
    except AssertionError:
        continue
    except parse_xml.BadSubtag:
        continue
    except KeyError:
        continue
    if 'title' not in edition:
        continue
    edition['ocaid'] = ia
    write_edition("ia:" + ia, edition)


print "finished"
