from catalog.get_ia import read_marc_file
from catalog.read_rc import read_rc
import web, os.path

# iterate through every MARC record on disk

rc = read_rc()

def sources():
    web.config.db_parameters = dict(dbn='postgres', db='ol_merge', user=rc['user'], pw=rc['pw'], host=rc['host'])
    web.config.db_printing = False
    web.load()

    return ((i.id, i.archive_id, i.name) for i in web.select('marc_source'))

def files(ia):
    endings = ['.mrc', '.marc', '.out', '.dat', '.records.utf8']
    def good(filename):
        return any(filename.endswith(e) for e in endings)

    dir = rc['marc_path'] + ia
    dir_len = len(dir) + 1
    files = []
    for dirpath, dirnames, filenames in os.walk(dir):
        files.extend(dirpath + "/" + f for f in sorted(filenames))
    return [(i[dir_len:], os.path.getsize(i)) for i in files if good(i)]

def all_files():
    endings = ['.mrc', '.marc', '.out', '.dat', '.records.utf8']
    def good(filename):
        return any(filename.endswith(e) for e in endings)

    dir = rc['marc_path']
    dir_len = len(dir) + 1
    for dirpath, dirnames, filenames in os.walk(dir):
        for f in sorted(f for f in filenames if good(f)):
            name = dirpath + "/" + f
            yield name, name[dir_len:], os.path.getsize(name)

def iter_parts():
    for source_id, ia, name in sources():
        for part, size in files(ia):
            full_part = ia + "/" + part
            filename = rc['marc_path'] + full_part
            assert os.path.exists(filename)
            f = open(filename)
            yield full_part, f

def iter_marc():
    for full_part, f in files(''):
        return read_marc_file(full_part, f)
