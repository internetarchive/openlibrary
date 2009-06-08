import web, re, httplib, sys, urllib2
import catalog.importer.pool as pool
from catalog.merge.merge_marc import build_marc
from catalog.read_rc import read_rc
from catalog.importer.load import build_query, east_in_by_statement, import_author
from catalog.utils.query import query, withKey
from catalog.importer.merge import try_merge
from catalog.importer.lang import add_lang
from catalog.get_ia import get_ia, urlopen_keep_trying
import catalog.marc.parse_xml as parse_xml
from time import time
import catalog.marc.fast_parse as fast_parse
sys.path.append('/home/edward/src/olapi')
from olapi import OpenLibrary, unmarshal

rc = read_rc()
ol = OpenLibrary("http://openlibrary.org")
ol.login('ImportBot', rc['ImportBot']) 


db = web.database(dbn='mysql', host=rc['ia_db_host'], user=rc['ia_db_user'], \
        passwd=rc['ia_db_pass'], db='archive')
db.printing = False

#iter = db.query("select identifier from metadata where scanner is not null and scanner != 'google' and noindex is null and mediatype='texts' and curatestate='approved' order by curatedate limit 10")
iter = db.query("select identifier from metadata where scanner is not null and scanner != 'google' and noindex is null and mediatype='texts' and curatestate='approved'")

t0 = time()
t_prev = time()
rec_no = 0
chunk = 50
load_count = 0

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
    prev = unmarshal(json.load(urllib2.urlopen(url)))
    assert prev['type'] == '/type/author'
    ol.save(key, prev, 'undelete author')

def undelete_authors(authors):
    for a in authors:
        if a['type'] == '/type/delete':
            undelete_author(a)
        else:
            print a
            assert a['type'] == '/type/author'

def add_source_records(key, ia):
    new = 'ia:' + ia
    sr = None
    e = ol.get(key)
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
        assert not any(a=='None' for a in e['authors'])
        print e['authors']
        authors = [ol.get(akey) for akey in e['authors']]
        authors = [ol.get(a['location']) if a['type'] == '/type/redirect' else a \
                for a in authors]
        e['authors'] = [a['key'] for a in authors]
        undelete_authors(authors)
    try:
        print ol.save(key, e, 'found a matching MARC record')
    except:
        print e
        raise
    if new_toc:
        new_edition = ol.get(key)
        # [{u'type': <ref: u'/type/toc_item'>}, ...]
        assert 'title' in new_edition['table_of_contents'][0]



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

for i in iter:
    ia = i.identifier
    if skip:
        if ia == 'blackrobe02coll':
            skip = False
        else:
            continue
    print ia
    if query({'type': '/type/edition', 'ocaid': ia}):
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
