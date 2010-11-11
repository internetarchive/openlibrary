from urllib2 import urlopen
from lxml.html import parse
from openlibrary.catalog.read_rc import read_rc
import os, sys, httplib, subprocess
from time import sleep

# httplib.HTTPConnection.debuglevel = 1 

# http://home.us.archive.org/~samuel/abouts3.txt

rc = read_rc()
accesskey = rc['s3_accesskey']
secret = rc['s3_secret']

def put_file(con, ia, filename):
    print 'uploading %s' % filename
    headers = {
        'authorization': "LOW " + accesskey + ':' + secret,
        'x-archive-queue-derive': 0,
    }
    url = 'http://s3.us.archive.org/' + ia + '/' + filename
    print url
    data = open(d + '/' + filename).read()
    for attempt in range(5):
        con.request('PUT', url, data, headers)
        try:
            res = con.getresponse()
        except httplib.BadStatusLine as bad:
            print 'bad status line:', bad.line
            raise
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

#print subprocess.Popen(["/usr/bin/perl", "get.pl"])
subprocess.call(["/usr/bin/perl", "get.pl"])

d = '/1/edward/lc_updates'
item_id = 'marc_loc_updates'
url = 'http://www.archive.org/download/' + item_id
existing = frozenset(l[2] for l in parse(url).getroot().iterlinks())

to_upload = set(os.listdir(d)) - existing

#to_upload = set(['v37.i26.records.utf8'])

for f in to_upload:
    con = httplib.HTTPConnection('s3.us.archive.org')
    con.connect()
    put_file(con, item_id, f)
    con.close()
    sleep(10)
