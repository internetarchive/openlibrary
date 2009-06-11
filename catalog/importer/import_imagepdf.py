import web,  sys
from catalog.utils.query import query, withKey
from catalog.read_rc import read_rc
sys.path.append('/home/edward/src/olapi')
from olapi import OpenLibrary, unmarshal

rc = read_rc()
ol = OpenLibrary("http://openlibrary.org")
ol.login('ImportBot', rc['ImportBot']) 

db = web.database(dbn='mysql', host=rc['ia_db_host'], user=rc['ia_db_user'], \
        passwd=rc['ia_db_pass'], db='archive')
db.printing = False

iter = db.query("select identifier from metadata where noindex is null and mediatype='texts' and scanner='google'")

for i in iter:
    ia = i.identifier
    print ia
    if query({'type': '/type/edition', 'ocaid': ia}):
        print 'already loaded'
        continue
    if query({'type': '/type/edition', 'source_records': 'ia:' + ia}):
        print 'already loaded'
        continue
