#!/usr/bin/env python

from openlibrary.catalog.read_rc import read_rc
from openlibrary import config
from ftplib import FTP
from time import sleep
from lxml import etree
import os, sys, httplib
import argparse

parser = argparse.ArgumentParser(description='Library of Congress MARC update')
parser.add_argument('--config', default='openlibrary.yml')
args = parser.parse_args()

config_file = args.config
config.load(config_file)
c = config.runtime_config['lc_marc_update']
base_url = 'http://openlibrary.org'
import_api_url = base_url + '/api/import'

def put_file(con, ia, filename, data):
    print 'uploading %s' % filename
    headers = {
        'authorization': "LOW " + c['s3_key'] + ':' + c['s3_secret'],
#        'x-archive-queue-derive': 0,
    }
    url = 'http://s3.us.archive.org/' + ia + '/' + filename
    print url
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
        sleep(5)
    print 'too many failed attempts'


url = 'http://archive.org/download/marc_loc_updates/marc_loc_updates_files.xml'

attempts = 10
wait = 5
for attempt in range(attempts):
    try:
        root = etree.parse(url).getroot()
        break
    except:
        if attempt == attempts-1:
            raise
        print 'error on attempt %d, retrying in %s seconds' % (attempt, wait)
        sleep(wait)

existing = set(f.attrib['name'] for f in root)
#existing.remove("v40.i32.report") # for testing

host = 'rs7.loc.gov'

to_upload = set()

def print_line(f):
    if 'books.test' not in f and f not in existing:
        to_upload.add(f)

def read_block(block):
    global data
    data += block

ftp = FTP(host)
ftp.set_pasv(False)
welcome = ftp.getwelcome()
ftp.login(c['lc_update_user'], c['lc_update_pass'])
ftp.cwd('/emds/books/all')
ftp.retrlines('NLST', print_line)

if to_upload:
    print welcome
else:
    ftp.close()
    sys.exit(0)

bad = open(c['log_location'] + 'lc_marc_bad_import', 'a')

def iter_marc(data):
    pos = 0
    while pos < len(data):
        length = data[pos:pos+5]
        int_length = int(length)
        yield (pos, int_length, data[pos:pos+int_length])
        pos += int_length

def login(h1):
    body = json.dumps({'username': 'LCImportBot', 'password': c['ol_bot_pass']})
    headers = {'Content-Type': 'application/json'}  
    h1.request('POST', base_url + '/account/login', body, headers)
    print base_url + '/account/login'
    res = h1.getresponse()

    print res.read()
    print 'status:', res.status
    assert res.status == 200
    cookies = res.getheader('set-cookie').split(',')
    cookie =  ';'.join([c.split(';')[0] for c in cookies])
    return cookie


h1 = httplib.HTTPConnection('openlibrary.org')
headers = {
    'Content-type': 'application/marc',
    'Cookie': login(h1),
}
h1.close()

item_id = 'marc_loc_updates'
for f in to_upload:
    data = ''
    print 'downloading', f
    ftp.retrbinary('RETR ' + f, read_block)
    print 'done'
    con = httplib.HTTPConnection('s3.us.archive.org')
    con.connect()
    put_file(con, item_id, f, data)
    con.close()

    loc_file = item_id + '/' + f
    for p, l, marc_data in iter_marc(data):
        loc = '%s:%d:%d' % (loc_file, p, l)
        headers['x-archive-meta-source-record'] = 'marc:' + loc
        try:
            h1 = httplib.HTTPConnection('openlibrary.org')
            h1.request('POST', import_api_url, marc_data, headers)
            try:
                res = h1.getresponse()
            except httplib.BadStatusLine:
                raise BadImport
            body = res.read()
            if res.status != 200:
                raise BadImport
            else:
                try:
                    reply = json.loads(body)
                except ValueError:
                    print 'not JSON:', `body`
                    raise BadImport
            assert res.status == 200
            print reply
            assert reply['success']
            h1.close()
        except BadImport:
            print >> bad, loc
            bad.flush()

ftp.close()
