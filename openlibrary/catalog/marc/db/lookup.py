import dbhash, sys
from catalog.read_rc import read_rc

rc = read_rc()
db = dbhash.open(rc['index_path'] + 'isbn_to_marc.dbm', 'r')
isbn = sys.argv[1]
if isbn in db:
    print db[isbn]
else:
    print isbn, 'not found'
