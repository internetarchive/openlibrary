import web, re, httplib, sys, urllib2, threading
import simplejson as json
from lxml import etree
import openlibrary.catalog.importer.pool as pool
from openlibrary.catalog.marc.marc_xml import read_marc_file, MarcXml, BlankTag, BadSubtag
from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.merge.merge_marc import build_marc
from openlibrary.catalog.read_rc import read_rc
from openlibrary.catalog.importer.load import build_query, east_in_by_statement, import_author
from openlibrary.catalog.utils import error_mail
from openlibrary.catalog.utils.query import query, withKey
from openlibrary.catalog.importer.merge import try_merge
from openlibrary.catalog.importer.update import add_source_records
from openlibrary.catalog.get_ia import get_ia, urlopen_keep_trying, NoMARCXML, bad_ia_xml, marc_formats, get_marc_ia, get_marc_ia_data
from openlibrary.catalog.title_page_img.load import add_cover_image
from openlibrary.solr.update_work import update_work, solr_update
#from openlibrary.catalog.works.find_works import find_title_redirects, find_works, get_books, books_query, update_works
from openlibrary.catalog.works.find_work_for_edition import find_matching_work
from openlibrary.catalog.marc import fast_parse, is_display_marc
from openlibrary.catalog.marc.parse import read_edition, NoTitle
from openlibrary.catalog.marc.marc_subject import subjects_for_work
from time import time, sleep
from openlibrary.api import OpenLibrary, unmarshal
from pprint import pprint
import argparse

parser = argparse.ArgumentParser(description='scribe loader')
parser.add_argument('--skip_hide_books', action='store_true')
parser.add_argument('--item_id')
args = parser.parse_args()

rc = read_rc()
ol = OpenLibrary("http://openlibrary.org")
ol.login('ImportBot', rc['ImportBot']) 

db_amazon = web.database(dbn='postgres', db='amazon')
db_amazon.printing = False

db = web.database(dbn='mysql', host=rc['ia_db_host'], user=rc['ia_db_user'], \
        passwd=rc['ia_db_pass'], db='archive')
db.printing = False

re_census = re.compile('^\d+(st|nd|rd|th)census')

re_edition_key = re.compile('^/(?:books|b)/(OL\d+M)$')

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

def load_binary(ia):
    url = archive_url + ia + '/' + ia + '_meta.mrc'
    f = urlopen_keep_trying(url)
    data = f.read()
    assert '<title>Internet Archive: Page Not Found</title>' not in data[:200]
    if len(data) != int(data[:5]):
        data = data.decode('utf-8').encode('raw_unicode_escape')
    assert len(data) == int(data[:5])
    return MarcBinary(data)

def load_xml(ia):
    url = archive_url + ia + '/' + ia + '_marc.xml'
    f = urlopen_keep_trying(url)
    root = etree.parse(f).getroot()
    if root.tag == '{http://www.loc.gov/MARC21/slim}collection':
        root = root[0]
    return MarcXml(root)
    edition = read_edition(rec)
    assert 'title' in edition
    return edition

def load(ia, use_binary=False):
    print "load", ia
    if not use_binary:
        try:
            rec = load_xml(ia)
            edition = read_edition(rec)
        except BadSubtag:
            use_binary = True
        except BlankTag:
            use_binary = True
    if use_binary:
        rec = load_binary(ia)
        edition = read_edition(rec)
    pprint(edition)
    assert 'title' in edition

    edition['ocaid'] = ia
    write_edition(ia, edition, rec)

def write_edition(ia, edition, rec):
    loc = 'ia:' + ia
    if ia == 'ofilhoprdigodr00mano':
        edition['languages'] = [{'key': '/languages/por'}]
    elif ia == 'dasrmischepriv00rein':
        edition['languages'] = [{'key': '/languages/ger'}]
    elif ia == 'derelephantenord00berl':
        del edition['languages']
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

    wkey = None
    subjects = subjects_for_work(rec)
    subjects.setdefault('subjects', []).append('Accessible book')
    if 'authors' in q:
        wkey = find_matching_work(q)
    if wkey:
        w = ol.get(wkey)
        need_update = False
        for k, subject_list in subjects.items():
            for s in subject_list:
                if s not in w.get(k, []):
                    w.setdefault(k, []).append(s)
                    need_update = True
        if need_update:
            ol.save(wkey, w, 'add subjects from new record')
    else:
        w = {
            'type': '/type/work',
            'title': q['title'],
        }
        if 'authors' in q:
            w['authors'] = [{'type':'/type/author_role', 'author': akey} for akey in q['authors']]
        w.update(subjects)

        wkey = ol.new(w, comment='initial import')

    q['works'] = [{'key': wkey}]
    for attempt in range(50):
        if attempt > 0:
            print 'retrying'
        try:
            pprint(q)
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
    key = '/b/' + re_edition_key.match(ret).group(1)
    pool.update(key, q)

    print 'add_cover_image'
    t = threading.Thread(target=add_cover_image, args=(ret, ia))
    t.start()
    return

    print 'run work finder'


    # too slow
    for a in authors:
        akey = a['key']
        title_redirects = find_title_redirects(akey)
        works = find_works(akey, get_books(akey, books_query(akey)), existing=title_redirects)
        works = list(works)
        updated = update_works(akey, works, do_updates=True)

fh_log = None

def write_log(ia, when, msg):
    print >> fh_log, (ia, when, msg)
    fh_log.flush()

hide_state_file = rc['state_dir'] + '/load_scribe_hide'

def hide_books(start):
    hide_start = open(hide_state_file).readline()[:-1]
    print 'hide start:', hide_start

    mend = []
    fix_works = set()
    db_iter = db.query("select identifier, collection, updated from metadata where (noindex is not null or curatestate='dark') and mediatype='texts' and scandate is not null and updated > $start order by scandate_dt", {'start': hide_start})
    last_updated = None
    for row in db_iter:
        ia = row.identifier
        if row.collection:
            collections = set(i.lower().strip() for i in row.collection.split(';'))
            if 'printdisabled' in collections or 'lendinglibrary' in collections:
                continue
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
        last_updated = row.updated
    print 'removing links from %d editions' % len(mend)
    if not mend:
        return
    print ol.save_many(mend, 'remove link')
    requests = []
    for wkey in fix_works:
        requests += update_work(withKey(wkey))
    if fix_works:
        solr_update(requests + ['<commit/>'], debug=True)
    print >> open(hide_state_file, 'w'), last_updated

def load_error_mail(ia, marc_display, subject):
    msg_from = 'load_scribe@archive.org'
    msg_to = ['edward@archive.org']
    subject += ': ' + ia
    msg = 'http://www.archive.org/details/%s\n' % ia
    msg += 'http://www.archive.org/download/%s\n'
    msg += '\n' + bad_binary
    error_mail(msg_from, msg_to, subject, msg)

def bad_marc_alert(bad_marc):
    msg_from = 'load_scribe@archive.org'
    msg_to = ['edward@archive.org']
    subject = '%d bad MARC' % len(bad_marc)
    msg = '\n'.join((
        'http://www.archive.org/details/%s\n' +
        'http://www.archive.org/download/%s\n\n' +
        '%s\n\n') % (ia, ia, `data`) for ia, data in bad_marc)
    error_mail(msg_from, msg_to, subject, msg)

if __name__ == '__main__':
    fh_log = open('/1/edward/logs/load_scribe', 'a')

    state_file = rc['state_dir'] + '/load_scribe'
    start = open(state_file).readline()[:-1]
    bad_marc_last_sent = time()
    bad_marc = []

    while True:

        if args.item_id:
            db_iter = db.query("select identifier, contributor, updated, noindex, collection from metadata where scanner is not null and mediatype='texts' and (not curatestate='dark' or curatestate is null) and scandate is not null and identifier=$item_id", {'item_id': args.item_id})
        else:
            if not args.skip_hide_books:
                hide_books(start)
            print 'start:', start
            db_iter = db.query("select identifier, contributor, updated, noindex, collection from metadata where scanner is not null and mediatype='texts' and (not curatestate='dark' or curatestate is null) and scandate is not null and updated between $start and date_add($start, interval 7 day) order by updated", {'start': start})
        t_start = time()
        for row in db_iter:
            if len(bad_marc) > 10 or time() - bad_marc_last_sent > (4 * 60 * 60):
                bad_marc_alert(bad_marc)
                bad_marc = []
                bad_marc_last_sent = time()

            ia = row.identifier
            if row.contributor == 'Allen County Public Library Genealogy Center':
                print 'skipping Allen County Public Library Genealogy Center'
                continue
            if row.collection:
                collections = set(i.lower().strip() for i in row.collection.split(';'))
            else:
                collections = set()
            if row.noindex:
                if not row.collection:
                    continue
                collections = set(i.lower().strip() for i in row.collection.split(';'))
                if not ('printdisabled' in collections or 'lendinglibrary' in collections):
                    continue
            if ia.startswith('annualreportspri'):
                print 'skipping:', ia
                continue
            if 'shenzhentest' in collections:
                continue

            if any('census' in c for c in collections):
                print 'skipping census'
                continue

            if re_census.match(ia) or ia.startswith('populationschedu') or ia.startswith('michigancensus') or 'census00reel' in ia or ia.startswith('populationsc1880'):
                print 'ia:', ia
                print 'collections:', list(collections)
                print 'census not marked correctly'
                continue
            assert 'passportapplicat' not in ia and 'passengerlistsof' not in ia
            if 'passportapplicat' in ia:
                print 'skip passport applications for now:', ia
                continue
            if 'passengerlistsof' in ia:
                print 'skip passenger lists', ia
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
                formats = marc_formats(ia)
            except urllib2.HTTPError as error:
                write_log(ia, when, "error: HTTPError: " + str(error))
                continue
            use_binary = False
            bad_binary = None
            if formats['bin']:
                print 'binary'
                use_binary = True
                marc_data = get_marc_ia_data(ia)
                if marc_data == '':
                    bad_binary = 'MARC binary empty string'
                if not bad_binary and is_display_marc(marc_data):
                    use_binary = False
                    bad_binary = marc_data
                    bad_marc.append((ia, marc_data))
                if not bad_binary:
                    try:
                        length = int(marc_data[0:5])
                    except ValueError:
                        bad_binary = "MARC doesn't start with number"
                if not bad_binary and len(marc_data) != length:
                    try:
                        marc_marc_data = marc_data.decode('utf-8').encode('raw_unicode_escape')
                    except:
                        bad_binary = "double UTF-8 decode error"
                if not bad_binary and len(marc_data) != length:
                    bad_binary = 'MARC length mismatch: %d != %d' % (len(marc_data), length)
                if not bad_binary and 'Internet Archive: Error' in marc_data:
                    bad_binary = 'Internet Archive: Error'
                if not bad_binary:
                    if str(marc_data)[6:8] != 'am': # only want books
                        print 'not a book!'
                        continue
                    try:
                        rec = fast_parse.read_edition(marc_data, accept_electronic = True)
                    except:
                        bad_binary = "MARC parse error"
            if bad_binary and not formats['xml']:
                load_error_mail(ia, bad_binary, 'bad MARC binary, no MARC XML')
                continue
            if not use_binary and formats['xml']:
                if bad_ia_xml(ia) and bad_binary:
                    load_error_mail(ia, bad_binary, 'bad MARC binary, bad MARC XML')
                    continue
                try:
                    rec = get_ia(ia)
                except (KeyboardInterrupt, NameError):
                    raise
                except NoMARCXML:
                    write_log(ia, when, "no MARCXML")
                    continue
                except urllib2.HTTPError as error:
                    write_log(ia, when, "error: HTTPError: " + str(error))
                    continue
            else:
                print 'skipping, no MARC'
                continue

            if not rec:
                write_log(ia, when, "error: no rec")
                continue
            if 'physical_format' in rec:
                format = rec['physical_format'].lower()
                if format.startswith('[graphic') or format.startswith('[cartograph'):
                    continue
            print rec

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
                load(ia, use_binary=use_binary)
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
                load(ia, use_binary=use_binary)
                write_log(ia, when, "loaded")
            print >> open(state_file, 'w'), row.updated
        start = row.updated
        secs = time() - t_start
        mins = secs / 60
        print "finished %d took mins" % mins
        if args.item_id:
            break
        print >> open(state_file, 'w'), start
        if mins < 30:
            print 'waiting'
            sleep(60 * 30 - secs)
