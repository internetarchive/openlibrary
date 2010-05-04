from openlibrary.catalog.marc.parse_xml import parse, xml_rec
from openlibrary.catalog.marc import read_xml
from openlibrary.api import OpenLibrary, unmarshal
from openlibrary.catalog.marc import fast_parse
from openlibrary.catalog.importer import pool
from openlibrary.catalog.merge.merge_marc import build_marc
from openlibrary.catalog.utils.query import query, withKey
from openlibrary.catalog.importer.merge import try_merge
import os, re, sys

ol = OpenLibrary("http://openlibrary.org")

re_census = re.compile('^\d+(st|nd|rd|th)census')
re_edition_key = re.compile('^/(?:b|books)/(OL\d+M)$')

scan_dir = '/2/edward/20century/scans/'

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

# no maps or cartograph

total = 74933
load_count = 0
num = 0
show_progress = True
check_for_existing = False
skip = 'internetforphysi00smit'
skip = None
add_src_rec = open('add_source_record', 'w')
new_book = open('new_book', 'w')
for line in open('/2/edward/20century/records_to_load'):
    num += 1
    full_rec = eval(line)
    item = full_rec['ia_id']
    if skip:
        if skip == item:
            skip = None
        else:
            continue
    if show_progress:
        print '%d/%d %d %.2f%% %s' % (num, total, load_count, (float(num) * 100.0) / total, item)
    if check_for_existing:
        if ol.query({'type': '/type/edition', 'ocaid': item}):
            print item, 'already loaded'
            load_count += 1
            continue
        if ol.query({'type': '/type/edition', 'source_records': 'ia:' + ia}):
            print 'already loaded'
            load_count += 1
            continue
    try:
        assert not re_census.match(item)
        assert 'passportapplicat' not in item
        assert len(full_rec.keys()) != 1
    except AssertionError:
        print item
        raise
    filename = '/2/edward/20century/scans/' + item[:2] + '/' + item + '/' + item + '_marc.xml'
    rec = read_xml.read_edition(open(filename))
    if 'full_title' not in rec:
        print "full_title missing", item
        continue
    if 'physical_format' in rec:
        format = rec['physical_format'].lower()
        if format.startswith('[graphic') or format.startswith('[cartograph'):
            print item, format
    index_fields = make_index_fields(rec)
    if not index_fields:
        print "no index_fields"
        continue
    #print index_fields

    edition_pool = pool.build(index_fields)
    if not edition_pool or not any(v for v in edition_pool.itervalues()):
        print >> new_book, rec
        continue

    print item, edition_pool
    e1 = build_marc(rec)
    print e1

    match = False
    seen = set()
    for k, v in edition_pool.iteritems():
        for edition_key in v:
#            edition_key = '/books/' + re_edition_key.match(edition_key).match(1)
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
                print 'add source records:', edition_key, item
                print (edition_key, item)
                print >> add_src_rec, (edition_key, item)
                #add_source_records(edition_key, ia)
                #write_log(ia, when, "found match: " + edition_key)
                match = True
                break
        if not match:
            print full_rec
            print >> new_book, full_rec
            break

sys.exit(0)
