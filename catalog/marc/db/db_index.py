from catalog.get_ia import read_marc_file
from time import time
from catalog.marc.fast_parse import index_fields, get_tag_lines
import os, os.path, re
from catalog.marc.all import all_files
from catalog.read_rc import read_rc

rc = read_rc()

fields = ['title', 'oclc', 'isbn', 'lccn']

out = dict((i, open(i, 'a')) for i in fields)
rec_id = 0
db_rec = open('recs', 'a')
db_file = open('files', 'a')
file_id = 0

re_escape = re.compile(r'[\n\r\t\0\\]')
trans = { '\n': '\\n', '\r': '\\r', '\t': '\\t', '\\': '\\\\', '\0': '', }

def esc_group(m):
    return trans[m.group(0)]
def esc(str): return re_escape.sub(esc_group, str)

def add_to_index(fh, value, key):
    if not value:
        return
    try:
        value = str(value)
    except UnicodeEncodeError:
        return
    print >> fh, "\t".join([key, esc(value)])

def process_record(pos, loc, data, file_id):
    global rec_id
    want = [
#        '006', # Material Characteristics
        '010', # LCCN
        '020', # ISBN
        '035', # OCLC
#        '130', '240', # work title
        '245', # title
#        '246', '730', '740' # other titles
    ]
    try:
        rec = index_fields(data, want, check_author = False)
    except:
        print loc
        raise
    if not rec:
        return
    field_size = { 'isbn': 16, 'oclc': 16, 'title': 25, 'lccn': 16 }
    if 'isbn' in rec:
        rec['isbn'] = [i for i in rec['isbn'] if len(i) <= 16]
    if 'oclc' in rec:
        rec['oclc'] = [i for i in rec['oclc'] if len(i) <= 16]
    if 'lccn' in rec:
        rec['lccn'] = [i for i in rec['lccn'] if len(i) <= 16]
    for k, v in rec.iteritems():
        if 'isbn' != k and any(len(i) > field_size[k] for i in v):
            print loc
            print rec
            assert False
    rec_id += 1
    (f, p, l) = loc[5:].split(':')
    print >> db_rec, '\t'.join([str(rec_id), str(file_id), p, l])

    for k, v in rec.iteritems():
        if not v:
            continue
        for i in v:
            add_to_index(out[k], i, str(rec_id)) 

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
chunk = 10000
total = 32856039


for name, part, size in all_files():
    f = open(name)
    print part
    file_id += 1
    print file_id, part, size
    print >> db_file, '\t'.join([str(file_id), part])
    filename = rc['marc_path'] + '/' + part
    if not os.path.exists(filename):
        print filename, 'missing'
    #    continue
    assert os.path.exists(filename)
    f = open(filename)
    for pos, loc, data in read_marc_file(part, f):
        rec_no +=1
        if rec_no % chunk == 0:
            t = time() - t_prev
            progress_update(rec_no, t)
            t_prev = time()
        process_record(pos, loc, data, file_id)

db_file.close()
db_rec.close()

print "closing files"
for v in out.values():
    v.close()
print "finished"
