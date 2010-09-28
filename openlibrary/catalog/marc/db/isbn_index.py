from catalog.get_ia import *
from catalog.read_rc import read_rc
from catalog.marc.sources import sources
from time import time
from catalog.marc.fast_parse import index_fields
import dbhash

# build an index of ISBN to MARC records

rc = read_rc()
#db = dbhash.open(rc['index_path'] + 'isbn_to_marc.dbm', 'w')
oclc_db = dbhash.open(rc['index_path'] + 'oclc.dbm', 'w')
title_db = dbhash.open(rc['index_path'] + 'title.dbm', 'w')

def add_to_db(db, isbn, loc):
    if isbn in db:
        db[isbn] += ' ' + loc
    else:
        db[isbn] = loc

def process_record(pos, loc, data):
    rec = index_fields(data, ['010'])
    if not rec:
        return
    for isbn in rec.get('oclc', []):
        try:
            add_to_db(oclc_db, str(isbn), loc)
        except (KeyboardInterrupt, NameError):
            raise
        except:
            pass
    for isbn in rec.get('title', []):
        try:
            add_to_db(title_db, str(isbn), loc)
        except (KeyboardInterrupt, NameError):
            raise
        except:
            pass

def progress_update(rec_no, t):
    remaining = total - rec_no
    rec_per_sec = chunk / t
    mins = (float((t/chunk) * remaining) / 60)
    print "isbn %d %.3f rec/sec" % (rec_no, rec_per_sec),
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

for ia, name in sources():
    print ia, name
    for part, size in files(ia):
        print part, size
        full_part = ia + "/" + part
        filename = rc['marc_path'] + full_part
        if not os.path.exists(filename):
            continue
        f = open(filename)
        for pos, loc, data in read_marc_file(full_part, f):
            rec_no +=1
            if rec_no % chunk == 0:
                t = time() - t_prev
                progress_update(rec_no, t)
                t_prev = time()
            process_record(pos, loc, data)

title_db.close()
oclc_db.close()
