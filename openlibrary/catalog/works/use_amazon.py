import os, re, sys, codecs, dbhash
from catalog.amazon.other_editions import find_others
from catalog.infostore import get_site
from catalog.read_rc import read_rc
from catalog.get_ia import get_data
from catalog.marc.build_record import build_record
from catalog.marc.fast_parse import get_tag_lines, get_all_subfields

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)
rc = read_rc()
db = dbhash.open(rc['index_path'] + 'isbn_to_marc.dbm', 'r')

site = get_site()

def get_records_from_marc(isbn):
    if isbn not in db:
        return
#    for loc in db[isbn].split(' '):
#        data = get_data(loc)
#        print loc
#        want = ['100', '110', '111', '240', '245', '260'] + [str(i) for i in range(500,600) if i not in (505, 520)]
#        for tag, line in get_tag_lines(data, set(want)):
#            sub = list(get_all_subfields(line))
#            if tag.startswith('5'):
#                assert len(sub) == 1 and sub[0][0] == 'a'
#                note = sub[0][1]
#                if note.find('ublish') != -1 or note.find('riginal') != -1:
#                    print '  note:', note
#                continue
#            print '  ', tag, sub
#        print
    recs = [(loc, build_record(get_data(loc))) for loc in db[isbn].split(' ')]
    keys = set()
    print
    for loc, rec in recs:
        print '  ', loc
#        keys.update([k for k in rec.keys() if k.find('title') != -1 or k in ('authors', 'title', 'contributions', 'work_title')])
        keys.update(rec.keys())
    print
    for k in keys:
        print k
        for loc, rec in recs:
            print "  ", rec.get(k, '###')
        print
    print

dir = sys.argv[1]
for filename in os.listdir(dir):
    if not filename[0].isdigit():
        continue
    l = find_others(filename, dir)
    if not l:
        continue
    print filename
    for k in site.things({'isbn_10': filename, 'type': '/type/edition'}):
        t = site.withKey(k)
        num = len(t.isbn_10)
        if num == 1:
            num = ''
        print '  OL:', k, t.title, num
        get_records_from_marc(filename)
    for asin, extra in l:
        print asin, extra
        things = site.things({'isbn_10': asin, 'type': '/type/edition'})
        if things:
            for k in things:
                t = site.withKey(k)
                num = len(t.isbn_10)
                if num == 1:
                    num = ''
                print '  OL:', k, t.title, num
        get_records_from_marc(asin)
    print "----"
