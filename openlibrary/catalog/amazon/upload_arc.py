from openlibrary.catalog.read_rc import read_rc
import httplib, web, time, sys, os

rc = read_rc()
accesskey = rc['s3_accesskey']
secret = rc['s3_secret']
arc_dir = '/2/edward/amazon/arc'

no_bucket_error = '<Code>NoSuchBucket</Code>'
internal_error = '<Code>InternalError</Code>'

done = [
    '20100210013733.arc',
    '20100210015013.arc',
    '20100210020316.arc',
    '20100210021445.arc',
    '20100210022726.arc',
    '20100210024019.arc',
    '20100210025249.arc',
    '20100210030609.arc',
    '20100210031752.arc',
    '20100210033024.arc',
    '20100210034255.arc',
    '20100210035501.arc',
    '20100210040904.arc',
    '20100210042130.arc',
    '20100210043351.arc',
    '20100210044553.arc',
    '20100210051017.arc',
    '20100210052258.arc',
    '20100210053601.arc',
    '20100210194700.arc',
    '20100210201110.arc',
    '20100212000643.arc',
    '20100212001705.arc',
    '20100212002656.arc',
    '20100212004512.arc',
    '20100212010934.arc',
    '20100212013415.arc',
    '20100212015925.arc',
    '20100212022248.arc',
    '20100212024600.arc',
    '20100212030916.arc',
    '20100212033221.arc',
    '20100212035616.arc',
    '20100212042043.arc',
    '20100212044622.arc',
    '20100212051112.arc',
    '20100212053604.arc',
    '20100212060140.arc',
    '20100212062647.arc',
    '20100212065128.arc',
    '20100212165731.arc',
    '20100212184748.arc',
    '20100212184807.arc',
    '20100212184822.arc',
    '20100212190147.arc',
    '20100212192404.arc',
    '20100212194513.arc',
    '20100212200700.arc',
    '20100212202810.arc',
    '20100212204852.arc',
    '20100212210951.arc',
    '20100212213032.arc',
    '20100212215107.arc'
]
    
def put_file(con, ia, filename, headers):
    print 'uploading %s' % filename
    headers['authorization'] = "LOW " + accesskey + ':' + secret
    url = 'http://s3.us.archive.org/' + ia + '/' + filename
    print url
    data = open(arc_dir + '/' + filename).read()
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

ia = 'amazon_book_crawl'
for filename in os.listdir(arc_dir):
    if filename in done:
        continue
    print filename
    if not filename.endswith('.arc'):
        continue
    con = httplib.HTTPConnection('s3.us.archive.org')
    con.connect()
    put_file(con, ia, filename, {})
    con.close()

