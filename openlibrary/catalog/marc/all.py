from openlibrary.catalog.get_ia import read_marc_file
from openlibrary.catalog.read_rc import read_rc
import web, os.path

# iterate through every MARC record on disk

rc = read_rc()

def files(ia):
    endings = ['.mrc', '.marc', '.out', '.dat', '.records.utf8']
    def good(filename):
        return any(filename.endswith(e) for e in endings)

    dir = rc['marc_path'] + '/' + ia
    dir_len = len(dir) + 1
    files = []
    for dirpath, dirnames, filenames in os.walk(dir):
        files.extend(dirpath + "/" + f for f in sorted(filenames))
    return [(i[dir_len:], os.path.getsize(i)) for i in files if good(i)]

def iter_marc(sources):
    rec_no = 0
    for ia in sources:
        for part, size in files(ia):
            full_part = ia + "/" + part
            filename = rc['marc_path'] + full_part
            assert os.path.exists(filename)
            f = open(filename)
            for pos, loc, data in read_marc_file(full_part, f):
                rec_no +=1
                yield rec_no, pos, loc, data
