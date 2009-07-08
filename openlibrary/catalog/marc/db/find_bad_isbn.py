#from catalog.get_ia import *
from catalog.get_ia import read_marc_file
from catalog.read_rc import read_rc
#from sources import sources
from time import time
from catalog.marc.fast_parse import index_fields, get_tag_lines
import web, os, os.path, re

# build an index of ISBN to MARC records

rc = read_rc()
web.config.db_parameters = dict(dbn='postgres', db='ol_merge', user=rc['user'], pw=rc['pw'], host=rc['host'])
web.config.db_printing = False
web.load()

def process_record(pos, loc, data):
    global rec_id
    want = [
#        '006', # Material Characteristics
#        '010', # LCCN
        '020', # ISBN
#        '035', # OCLC
#        '130', '240', # work title
#        '245', # title
#        '246', '730', '740' # other titles
    ]
    rec = index_fields(data, want, check_author = False)
    field_size = { 'isbn': 16, 'oclc': 16, 'title': 25, 'lccn': 16 }
    if not rec or 'isbn' not in rec:
        return
    for isbn in rec['isbn']:
        if ';' in isbn:
            print loc
            print rec
        assert ';' not in isbn
    too_long = any(len(i) > 16 for i in rec['isbn'])
    if not too_long:
        return
    print loc
    print rec
    assert not too_long
    
    for a, length in field_size:
        if a not in rec:
            continue
        too_long = any(len(i) > size for i in rec[a])
        if not too_long:
            continue
        print loc
        print rec
        assert too_long
#    rec = list(get_tag_lines(data, want))
    return

def progress_update(rec_no, t):
    remaining = total - rec_no
    rec_per_sec = chunk / t
    mins = (float((t/chunk) * remaining) / 60)
    print "%d %.3f rec/sec" % (rec_no, rec_per_sec),
    if mins > 1440:
        print "%.3f days left" % (mins / 1440)
    elif mins > 60:
        print "%.3f hours left" % (mins / 60)
    else:
        print "%.3f minutes left" % mins

t_prev = time()
rec_no = 0
chunk = 1000
total = 32856039

def sources():
    return ((i.id, i.archive_id, i.name) for i in web.select('marc_source'))

def files(ia):
    dir = rc['marc_path'] + ia
    dir_len = len(dir) + 1
    files = []
    for dirpath, dirnames, filenames in os.walk(dir):
        files.extend(dirpath + "/" + f for f in sorted(filenames))
    return [(i[dir_len:], os.path.getsize(i)) for i in files]

for source_id, ia, name in sources():
    print
    print source_id, ia, name
    for part, size in files(ia):
        print ia, part, size
        full_part = ia + "/" + part
        filename = rc['marc_path'] + full_part
        if not os.path.exists(filename):
            print filename, 'missing'
        #    continue
        assert os.path.exists(filename)
        f = open(filename)
        for pos, loc, data in read_marc_file(full_part, f):
            rec_no +=1
            if rec_no % chunk == 0:
                t = time() - t_prev
                progress_update(rec_no, t)
                t_prev = time()
            process_record(pos, loc, data)

