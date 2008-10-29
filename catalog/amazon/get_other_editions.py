from catalog.read_rc import read_rc
import web, urllib2, sys, os.path
from time import time

rc = read_rc()
web.config.db_parameters = dict(dbn='postgres', db=rc['db'], user=rc['user'], pw=rc['pw'], host=rc['host'])
web.config.db_printing = False
web.load()
dir = sys.argv[1]

chunk = 10
t0 = time()
isbn_iter = web.query('select value from edition_str where key_id=30')
for i, row in enumerate(isbn_iter):
    isbn = row.value
    dest = dir + '/' + isbn
    if os.path.exists(dest):
        continue
    if len(isbn) != 10:
        continue
    url = 'http://www.amazon.com/dp/other-editions/' + isbn
    try:
        page = urllib2.urlopen(url).read()
    except urllib2.HTTPError, error:
        if error.code != 404:
            raise
        page = ''
    open(dest, 'w').write(page)
    if i % chunk == 0:
        t1 = time() - t0
        rec_per_sec = float(i) / float(t1)
        print "%s %s %.2f rec/sec" % (url, isbn, rec_per_sec)
