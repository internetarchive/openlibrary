from catalog.read_rc import read_rc
import web, sys
rc = read_rc()
web.config.db_parameters = dict(dbn='mysql', db='archive', user=rc['ia_db_user'], pw=rc['ia_db_pass'], host=rc['ia_db_host'])
web.load()

row = list(web.select('metadata', what='count(*) as num', where="scanner = 'google' and mediatype='texts' and noindex is null"))
print 'Image PDFs:', row[0].num

row = list(web.select('metadata', what='count(*) as num', where="scanner != 'google' and noindex is null and mediatype='texts'"))
print 'Scanned books:', row[0].num

sys.exit(0)

for row in web.select('metadata', scanner='google'):
    print row.identifier
