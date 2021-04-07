import web, re, httplib, sys, urllib2
from openlibrary.catalog.read_rc import read_rc

rc = read_rc()
db = web.database(dbn='mysql', host=rc['ia_db_host'], user=rc['ia_db_user'], passwd=rc['ia_db_pass'], db='archive')
db.printing = False

iter = db.query("select identifier, updated from metadata where scanner is not null and noindex is not null and mediatype='texts' and (curatestate='approved' or curatestate is null) and scandate is not null order by updated")

for row in iter:
    print row.identifier
