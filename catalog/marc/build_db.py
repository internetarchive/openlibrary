from sources import sources
from catalog.marc.fast_parse import index_fields, read_file
from catalog.get_ia import files
from catalog.read_rc import read_rc
from time import time
import os, web

rc = read_rc()

web.config.db_parameters = dict(dbn='postgres', db='marc_records', user=rc['user'], pw=rc['pw'], host=rc['host'])
web.config.db_printing = False
web.load()

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

fields = ['isbn', 'oclc', 'lccn', 'call_number', 'title']

def process_record(file_id, pos, length, data):
    rec = index_fields(data, ['001', '010', '020', '035', '245'], check_author = False)
    if not rec:
        return
    extra = dict((f, rec[f][0]) for f in ('title', 'lccn', 'call_number') if f in rec)
    rec_id = web.insert('rec', marc_file = file_id, pos=pos, len=length, **extra)
    for f in (f for f in ('isbn', 'oclc') if f in rec):
        for v in rec[f]:
            web.insert(f, seqname=False, rec=rec_id, value=v)

t_prev = time()
rec_no = 0
chunk = 1000
total = 32856039

for ia, name in sources():
    print ia, name
    for part, size in files(ia):
        file_id = web.insert('files', ia=ia, part=part)
        print part, size
        full_part = ia + "/" + part
        filename = rc['marc_path'] + full_part
        if not os.path.exists(filename):
            continue
        pos = 0
        for data, length in read_file(open(filename)):
            pos += length
            rec_no +=1
            if rec_no % chunk == 0:
                t = time() - t_prev
                progress_update(rec_no, t)
                t_prev = time()
            process_record(file_id, pos, length, data)

print rec_no
