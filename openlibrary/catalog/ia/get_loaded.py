from catalog.read_rc import read_rc
import web, sys
rc = read_rc()
web.config.db_parameters = dict(dbn='postgres', db=rc['db'], user=rc['user'], pw=rc['pw'], host=rc['host'])
web.load()

iter = web.select('version', what='machine_comment', where="machine_comment like 'ia:%%'")

for row in iter:
    print row.machine_comment[3:]
