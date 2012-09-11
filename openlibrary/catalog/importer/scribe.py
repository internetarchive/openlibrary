#!/usr/bin/python
from subprocess import Popen, PIPE
from openlibrary.utils.ia import find_item, FindItemError
from openlibrary.api import OpenLibrary
from openlibrary.catalog.read_rc import read_rc
from openlibrary.catalog.get_ia import marc_formats, get_marc_ia_data
from openlibrary.catalog.marc import is_display_marc
from time import sleep, time
from pprint import pprint

import MySQLdb
import re, urllib2, httplib, json, codecs, socket, sys

ol = OpenLibrary('http://openlibrary.org/')

rc = read_rc()

base_url = 'http://openlibrary.org'

ia_db_host = 'dbmeta.us.archive.org'
ia_db_user = 'archive'
ia_db_pass = Popen(["/opt/.petabox/dbserver"], stdout=PIPE).communicate()[0]

re_census = re.compile('^\d+(st|nd|rd|th)census')

fields = ['identifier', 'contributor', 'updated', 'noindex', 'collection', 'format', 'boxid']
sql_fields = ', '.join(fields)

scanned_start = open('scanned_start').readline()[:-1]

ignore_noindex = set(['printdisabled', 'lendinglibrary', 'inlibrary'])

def login(h1):
    body = json.dumps({'username': 'ImportBot', 'password': rc['ImportBot']})
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
h1.set_debuglevel(1)
cookie = login(h1)
h1.close()

bad = open('bad_import', 'a')
bad_lang = open('bad_lang', 'a')
logfile = open('log', 'a')
logfile.flush()

class BadImport (Exception):
    pass

class BadLang (Exception):
    pass

import_api_url = base_url + '/api/import'
def post_to_import_api(ia, marc_data, contenttype, subjects = [], boxid = None, scanned=True):
    print "POST to /api/import:", (ia, len(marc_data))

    cover_url = 'http://www.archive.org/download/' + ia + '/page/' + ia + '_preview.jpg'

    headers = {
        'Content-type': contenttype,
        'Cookie': cookie,
        'x-archive-meta-source-record': 'ia:' + ia,
    }
    if scanned:
        headers['x-archive-meta-cover'] = cover_url
        headers['x-archive-meta-ocaid'] = ia
    else:
        headers['x-archive-meta-ia-loaded-id'] = ia

    for num, s in enumerate(subjects):
        headers['x-archive-meta%02d-subject' % (num + 1)] = s

    if boxid:
        headers['x-archive-meta-ia-box-id'] = boxid

    print import_api_url
    h1 = httplib.HTTPConnection('openlibrary.org')
    #h1.set_debuglevel(1)
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
    print >> logfile, reply
    print reply
    if not reply['success'] and reply['error'].startswith('invalid language code:'):
        raise BadLang
    assert reply['success']
    h1.close()

def check_marc_data(marc_data):
    if marc_data == '':
        return 'MARC binary empty string'
    if is_display_marc(marc_data):
        return 'display MARC'
    try:
        length = int(marc_data[0:5])
    except ValueError:
        return "MARC doesn't start with number"
    double_encode = False
    if len(marc_data) != length:
        try:
            marc_data = marc_data.decode('utf-8').encode('raw_unicode_escape')
            double_encode = True
        except:
            return "double UTF-8 decode error"
    if len(marc_data) != length:
        return 'MARC length mismatch: %d != %d' % (len(marc_data), length)
    if str(marc_data)[6:8] != 'am': # only want books
        return 'not a book!'
    if double_encode:
        return 'double encoded'
    return None

def load_book(ia, collections, boxid, scanned=True):
    if ia.startswith('annualreportspri'):
        print 'skipping:', ia
        return
    if 'shenzhentest' in collections:
        return

    if any('census' in c for c in collections):
        print 'skipping census'
        return

    if re_census.match(ia) or ia.startswith('populationschedu') or ia.startswith('michigancensus') or 'census00reel' in ia or ia.startswith('populationsc1880'):
        print 'ia:', ia
        print 'collections:', list(collections)
        print 'census not marked correctly'
        return
    try:
        host, path = find_item(ia)
    except socket.timeout:
        print 'socket timeout:', ia
        return
    except FindItemError:
        print 'find item error:', ia
    bad_binary = None
    try:
        formats = marc_formats(ia, host, path)
    except urllib2.HTTPError as error:
        return

    if formats['bin']: # binary MARC
        marc_data = get_marc_ia_data(ia, host, path)
        assert isinstance(marc_data, str)
        marc_error = check_marc_data(marc_data)
        if marc_error == 'double encode':
            marc_data = marc_data.decode('utf-8').encode('raw_unicode_escape')
            marc_error = None
        if marc_error:
            return
        contenttype = 'application/marc'
    elif formats['xml']: # MARC XML
        return # waiting for Raj to fox MARC XML loader
        marc_data = urllib2.urlopen('http://' + host + path + '/' + ia + '_meta.xml').read()
        contenttype = 'text/xml'
    else:
        return
    subjects = []
    if scanned:
        if 'lendinglibrary' in collections:
            subjects += ['Protected DAISY', 'Lending library']
        elif 'inlibrary' in collections:
            subjects += ['Protected DAISY', 'In library']
        elif 'printdisabled' in collections:
            subjects.append('Protected DAISY')

    if not boxid:
        boxid = None
    try:
        post_to_import_api(ia, marc_data, contenttype, subjects, boxid, scanned=scanned)
    except BadImport:
        print >> bad, ia
        bad.flush()
    except BadLang:
        print >> bad_lang, ia
        bad_lang.flush()

if __name__ == '__main__':
    skip = 'troubleshootingm00bige'
    skip = None
    while True:
        loaded_start = open('loaded_start').readline()[:-1]
        print loaded_start

        conn = MySQLdb.connect(host=ia_db_host, user=ia_db_user, \
                passwd=ia_db_pass, db='archive')

        cur = conn.cursor()
        cur.execute("select " + sql_fields + \
            " from metadata" + \
            " where identifier not like '%%test%%' and mediatype='texts'" + \
                " and (not curatestate='dark' or curatestate is null)" + \
                " and (collection like 'inlibrary%%' or collection like 'lendinglibrary%%' or (scanner is not null and scancenter is not null and scandate is null))" + \
                " and updated > %s" + \
                " order by updated", [loaded_start])
        t_start = time()

        for ia, contributor, updated, noindex, collection, ia_format, boxid in cur.fetchall():
            print updated, ia
            if contributor == 'Allen County Public Library Genealogy Center':
                print 'skipping Allen County Public Library Genealogy Center'
                continue
            collections = set()
            if collection:
                collections = set(i.lower().strip() for i in collection.split(';'))

            q = {'type': '/type/edition', 'ocaid': ia}
            if ol.query(q):
                continue
            q = {'type': '/type/edition', 'ia_loaded_id': ia}
            if ol.query(q):
                continue
            load_book(ia, collections, boxid, scanned=False)
            print >> open('loaded_start', 'w'), updated
        cur.close()

        scanned_start = open('scanned_start').readline()[:-1]
        print scanned_start
        cur = conn.cursor()
        cur.execute("select " + sql_fields + \
            " from metadata" + \
            " where mediatype='texts'" + \
                " and (not curatestate='dark' or curatestate is null)" + \
                " and format is not null " + \
                " and (collection like 'inlibrary%%' or collection like 'lendinglibrary%%' or scandate is not null)" + \
                " and updated > %s" + \
                " order by updated", [scanned_start])
        t_start = time()

        for ia, contributor, updated, noindex, collection, ia_format, boxid in cur.fetchall():
            print updated, ia
            if skip:
                if ia == skip:
                    skip = None
                continue
            if ia == 'treatiseonhistor00dixo':
                continue
            if ia == 'derheiligejohann00nean': # language is 'ge ' should be 'ger'
                continue
            if ia == 'lenseignementetl00kuhn': # language is ' fr' should be 'fre'
                continue
            if ia == 'recherchesetnote00gali': # language is 'efr' should be 'fre'
                continue
            if ia == 'placenamesinstra00macd': # language is 'd  '
                continue
            if ia == 'conaantnoanynjia00walk': # language is 'max':
                continue
            if 'pdf' not in ia_format.lower():
                continue # scancenter and billing staff often use format like "%pdf%" as a proxy for having derived

            collections = set()
            if noindex:
                if not collection:
                    continue
                collections = set(i.lower().strip() for i in collection.split(';'))
                if not ignore_noindex & collections:
                    continue
            if 'inlibrary' not in collections and contributor == 'Allen County Public Library Genealogy Center':
                print 'skipping Allen County Public Library Genealogy Center'
                continue

            load_book(ia, collections, boxid, scanned=True)
            print >> open('scanned_start', 'w'), updated

        cur.close()
        secs = time() - t_start
        mins = secs / 60
        print "finished %d took mins" % mins
        if mins < 30:
            print 'waiting'
            sleep(60 * 30 - secs)
