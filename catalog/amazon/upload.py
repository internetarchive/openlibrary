from catalog.read_rc import read_rc
import httplib, web, time, sys
from datetime import date, timedelta

rc = read_rc()
accesskey = rc['s3_accesskey']
secret = rc['s3_secret']

db = web.database(dbn='mysql', host=rc['ia_db_host'], user=rc['ia_db_user'], \
        passwd=rc['ia_db_pass'], db='archive')
db.printing = False

crawl_dir = '/1/edward/amazon/crawl'
collection = 'ol_data'
mediatype = 'data'

con = httplib.HTTPConnection('s3.us.archive.org')
con.connect()

def wait_for_upload(ia):
    while True:
        rows = list(db.select('catalog', where='identifier = $ia', vars={'ia': ia}))
        if len(rows) == 0:
            return
        print "\r", len(rows), 'tasks still running',
        time.sleep(5)
    print '\ndone'

no_bucket_error = '<Code>NoSuchBucket</Code>'
internal_error = '<Code>InternalError</Code>'

def put_file(con, ia, filename, headers):
    print 'uploading %s' % filename
    headers['authorization'] = "LOW " + accesskey + ':' + secret
    url = 'http://s3.us.archive.org/' + ia + '/' + filename
    print url
    data = open(crawl_dir + '/' + filename).read()
    for attempt in range(5):
        con.request('PUT', url, data, headers)
        res = con.getresponse()
        body = res.read()
        if '<Error>' not in body:
            return
        print 'error'
        print body
        if no_bucket_error not in body and internal_error not in body:
            sys.exit(0)
        print 'retry'
        time.sleep(5)
    print 'too many failed attempts'

def create_item(con, ia, cur_date):
    headers = {
        'x-amz-auto-make-bucket': 1,
        'x-archive-meta01-collection': collection,
        'x-archive-meta-mediatype': mediatype,
        'x-archive-meta-language': 'eng',
        'x-archive-meta-title': 'Amazon crawl ' + cur_date,
        'x-archive-meta-description': 'Crawl of Amazon. Books published on ' + cur_date + '.',
        'x-archive-meta-year': cur_date[:4],
        'x-archive-meta-date': cur_date.replace('-', ''),
    }

    filename =  'index.' + cur_date
    put_file(con, ia, filename, headers)

def upload_index(con, cur_date):
    ia = 'amazon_crawl.' + cur_date 

    create_item(con, ia, cur_date)
    wait_for_upload(ia)
    time.sleep(5)

    put_file(con, ia, 'amazon.' + cur_date, {})
    put_file(con, ia, 'cats.' + cur_date, {})
    put_file(con, ia, 'list.' + cur_date, {})

one_day = timedelta(days=1)
cur = date(2009, 4, 26) # start from
while True:
    print cur
    upload_index(con, str(cur))
    cur -= one_day

con.close()
