import web, os.path
from catalog.get_ia import read_marc_file
from catalog.read_rc import read_rc
from catalog.marc.fast_parse import get_first_tag, get_all_subfields
from catalog.utils.query import query_iter

marc_index = web.database(dbn='postgres', db='marc_index')
marc_index.printing = False

rc = read_rc()

def get_keys(loc):
    assert loc.startswith('marc:')
    vars = {'loc': loc[5:]}
    db_iter = marc_index.query('select k from machine_comment where v=$loc', vars)
    mc = list(db_iter)
    if mc:
        return [r.k for r in mc]
    iter = query_iter({'type': '/type/edition', 'source_records': loc})
    return [e['key'] for e in iter]

def files():
    endings = ['.mrc', '.marc', '.out', '.dat', '.records.utf8']
    def good(filename):
        return any(filename.endswith(e) for e in endings)

    dir = rc['marc_path']
    dir_len = len(dir) + 1
    for dirpath, dirnames, filenames in os.walk(dir):
        for f in sorted(f for f in filenames if good(f)):
            name = dirpath + "/" + f
            yield name, name[dir_len:], os.path.getsize(name)

def percent(a, b):
    return "%.2f%%" % (float(a * 100.0) / b)

chunk = 10000

books = 0
has_041 = 0
has_a = 0
has_h = 0
has_2 = 0
i2 = 0
i1_0 = 0
i1_1 = 0
for name, part, size in files():
    f = open(name)
    print part
    for pos, loc, data in read_marc_file(part, f):
        if str(data)[6:8] != 'am': # only want books
            continue
        books += 1
        line = get_first_tag(data, set(['041']))
        if not line:
            continue
        has_041 += 1
        if line[0] == '0':
            i1_0 += 1
        if line[0] == '1':
            i1_1 += 1
        subfields = list(get_all_subfields(line))
        print loc
        keys = get_keys(loc)
        print keys, line[0:2], subfields
        continue
        if line[1] != ' ':
            i2 += 1
            print 'i2:', line[0:2], subfields
        if '\x1fa' in line:
            has_a +=1
        else:
            print 'no a:', line[0:2], subfields
        if '\x1fh' in line:
            has_h +=1
        if '\x1f2' in line:
            has_2 +=1
            print 'has 2:', line[0:2], subfields
        if has_041 % chunk == 0:
            print books, percent(has_041, books), percent(i1_0, has_041), \
                percent(i1_1, has_041), i2, percent(has_a, has_041), \
                percent(has_h, has_041), has_2
#        print total, line[0:2], list(get_all_subfields(line))
