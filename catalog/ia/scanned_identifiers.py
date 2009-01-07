from catalog.read_rc import read_rc
import web, sys
rc = read_rc()
web.config.db_parameters = dict(dbn='mysql', db='archive', user=rc['ia_db_user'], pw=rc['ia_db_pass'], host=rc['ia_db_host'])
web.load()

iter = web.select('metadata', where="scanner != 'google' and noindex is null and mediatype='texts'")

for row in iter:
    print row.identifier
