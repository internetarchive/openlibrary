#from catalog.get_ia import *
from catalog.get_ia import read_marc_file
from catalog.read_rc import read_rc
#from sources import sources
from time import time
from catalog.marc.fast_parse import index_fields
import web, os, os.path

# build an index of ISBN to MARC records

rc = read_rc()
web.config.db_parameters = dict(dbn='postgres', db='ol_merge', user=rc['user'], pw=rc['pw'], host=rc['host'])
web.config.db_printing = False
web.load()

fields = ['title', 'oclc', 'isbn', 'lccn', 'work_title', 'other_titles']
#db = dbhash.open(rc['index_path'] + 'isbn_to_marc.dbm', 'w')

def add_to_db(isbn, loc):
    print loc, isbn
    return
    if isbn in db:
        db[isbn] += ' ' + loc
    else:
        db[isbn] = loc

def process_record(pos, loc, data):
    #rec = index_fields(data, ['020'])
    want = ['006', '010', '020', '035', '245']
    rec = index_fields(data, want)
    print loc
    print rec
    return
    if not rec or 'isbn' not in rec:
        return
    for isbn in rec['isbn']:
        try:
            add_to_db(str(isbn), loc)
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

def sources():
    return ((i.archive_id, i.name) for i in web.select('marc_source'))

def files(ia):
    dir = rc['marc_path'] + ia + '/'
    return [(i, os.path.getsize(dir + i)) for i in os.listdir(dir) if os.path.isfile(dir + i)]

for ia, name in sources():
    print
    print ia, name
    for part, size in files(ia):
        print ia, part, size
        full_part = ia + "/" + part
        filename = rc['marc_path'] + full_part
        assert os.path.exists(filename)
        if not os.path.exists(filename):
            print filename, 'missing'
            continue
        f = open(filename)
        for pos, loc, data in read_marc_file(full_part, f):
            rec_no +=1
            if rec_no % chunk == 0:
                t = time() - t_prev
                progress_update(rec_no, t)
                t_prev = time()
#            print pos, loc
            process_record(pos, loc, data)

#db.close()
