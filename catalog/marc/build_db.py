from sources import sources
from catalog.marc.fast_parse import index_fields, read_file
from catalog.get_ia import files

def progress_update(rec_no, t):
    remaining = total - rec_no
    rec_per_sec = chunk / t
    mins = (float((t/chunk) * remaining) / 60)
    print "isbn %d %d %.3f rec/sec" % (rec_no, good, rec_per_sec),
    if mins > 1440:
        print "%.3f days left" % (mins / 1440)
    elif mins > 60:
        print "%.3f hours left" % (mins / 60)
    else:
        print "%.3f minutes left" % mins

def process_record(pos, length, data):
    rec = index_fields(data, ['001', '010', '020', '035', '245'])
    print pos, length
    print rec

for ia, name in sources():
    print ia, name
    for part, size in files(ia):
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
            process_record(pos, length, data)
