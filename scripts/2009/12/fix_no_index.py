from openlibrary.catalog.utils.query import query, withKey
from openlibrary.api import OpenLibrary, unmarshal
from openlibrary.catalog.read_rc import read_rc

rc = read_rc()
ol = OpenLibrary("http://openlibrary.org")
ol.login('ImportBot', rc['ImportBot'])

to_fix = []
num = 0
for line in open('no_index'):
    for e in query({'type': '/type/edition', 'title': None, 'ocaid': line[:-1]}):
        num += 1
        print(num, e['key'], repr(e['title']), line[:-1])
        e2 = ol.get(e['key'])
        del e2['ocaid']
        to_fix.append(e2)

ol.save_many(to_fix, 'remove link')
