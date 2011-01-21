from openlibrary.utils.ia import find_item
from openlibrary.catalog.read_rc import read_rc
from openlibrary.catalog.utils.query import query, withKey, has_cover
from subprocess import Popen, PIPE
import web, re, urllib, sys
import xml.etree.ElementTree as et
import xml.parsers.expat, socket # for exceptions
import httplib
from time import sleep

re_single_cover = re.compile('^\[(\d+)\]$')
re_remove_xmlns = re.compile(' xmlns="[^"]+"')

fh_log = open('/1/edward/logs/covers2', 'a')

def write_log(ol, ia, url):
    print >> fh_log, (ol, ia, url)
    fh_log.flush()

def parse_scandata_xml(f):
    xml = f.read()
    xml = re_remove_xmlns.sub('', xml)
    #tree = et.parse(f)
    tree = et.fromstring(xml)
    leaf = None
    leafNum = None
    cover = None
    title = None
    for e in tree.find('pageData'):
        assert e.tag == 'page'
        leaf = int(e.attrib['leafNum'])
        if leaf > 25: # enough
            break
        page_type = e.findtext('pageType')
        if page_type == 'Cover':
            cover = leaf
        elif page_type == 'Title Page' or page_type == 'Title':
            title = leaf
            break
    return (cover, title)

def find_title_leaf_et(ia_host, ia_path, url):
    f = urllib.urlopen(url)
    try:
        return parse_scandata_xml(f)
    except xml.parsers.expat.ExpatError:
        print url
        return (None, None)

def jp2_zip_test(ia_host, ia_path, ia):
    conn = httplib.HTTPConnection(ia_host)
    conn.request('HEAD', ia_path + "/" + ia + "_jp2.zip")
    r1 = conn.getresponse()
    try:
        assert r1.status in (200, 403, 404)
    except AssertionError:
        print r1.status, r1.reason
        raise
    return r1.status

def scandata_url(ia_host, ia_path, item_id):
    conn = httplib.HTTPConnection(ia_host)
    conn.request('HEAD', ia_path + "/scandata.zip")
    r = conn.getresponse()
    try:
        assert r.status in (200, 403, 404)
    except AssertionError:
        print r.status, r.reason
        raise
    if r.status == 200:
        None
    conn = httplib.HTTPConnection(ia_host)
    path = ia_path + "/" + item_id + "_scandata.xml"
    conn.request('HEAD', path)
    r = conn.getresponse()
    try:
        assert r.status in (200, 403, 404)
    except AssertionError:
        print ia_host, path
        print r.status, r.reason
        raise
    return 'http://' + ia_host + path if r.status == 200 else None

def scandata_zip_test(ia_host, ia_path):
    conn = httplib.HTTPConnection(ia_host)
    conn.request('HEAD', ia_path + "/scandata.zip")
    r1 = conn.getresponse()
    try:
        assert r1.status in (200, 403, 404)
    except AssertionError:
        print r1.status, r1.reason
        raise
    return r1.status



def urlread(url):
    return urllib.urlopen(url).read()

def post_cover(ol, source_url):
    param = urllib.urlencode({'olid': ol[3:], 'source_url': source_url})
    headers = {"Content-type": "application/x-www-form-urlencoded"}
    conn = httplib.HTTPConnection("covers.openlibrary.org", timeout=20)
    conn.request("POST", "/b/upload", param, headers)
    r1 = conn.getresponse()
    print r1.status, r1.reason
    if r1.status not in (200, 303, 500):
        open('upload.html', 'w').write(r1.read())
        print r1.getheaders()
        print r1.msg
        sys.exit()
    conn.close()

def post(ol, ia, ia_host, ia_path, cover, title):
    use_cover = False
    if title is None:
        if cover is None:
            return
        use_cover = True
#    http://covers.openlibrary.org/b/query?olid=OL7232120M
    if False and not use_cover:
        data = urlread('http://openlibrary.org/query.json?key=/b/OL7232119M&publish_date=')
        try:
            ret = eval(data)
        except:
            print `data`
        pub_date = ret[0]['publish_date']
        use_cover = pub_date.isdigit() and int(pub_date) > 1955
    leaf = cover if use_cover else title
    source_url = "http://%s/GnuBook/GnuBookImages.php?zip=%s/%s_jp2.zip&file=%s_jp2/%s_%04d.jp2" % (ia_host, ia_path, ia, ia, ia, leaf)
#    print leaf, source_url
    query = 'http://covers.openlibrary.org/b/query?olid=' + ol[3:]
    #print query
    if use_cover:
        print 'use_cover',
    print 'http://openlibrary.org' + ol
    for attempt in range(5):
        if attempt > 0:
            print 'trying again (%d)' % attempt
        try:
            ret = urlread(query).strip()
        except IOError:
            continue
        print ret
        if not re_single_cover.match(ret):
            print "unexpected reply: '%s'" % ret
            break
        try:
            write_log(ol, ia, source_url)
            post_cover(ol, source_url)
        except socket.timeout:
            print 'socket timeout'
            break
        except httplib.BadStatusLine:
            print 'bad status line'
            continue
        break

bad_hosts = set()

def find_img(item_id):
    e = query({'type':'/type/edition', 'source_records':'ia:' + item_id})
    if len(e) != 1:
        print 'no source_records:', e
        e = query({'type':'/type/edition', 'ocaid': item_id})
        if len(e) != 1:
            print 'no ocaid:', e
            return
    ol = e[0]['key']
    (ia_host, ia_path) = find_item(item_id)

    if not ia_host:
        print 'no host', item_id, ia_host
        return
    if ia_host in bad_hosts:
        print 'bad_host'
    try:
        url = scandata_url(ia_host, ia_path, item_id)
        if not url:
            return
    except socket.error:
        print 'socket error:', ia_host
        bad_hosts.add(ia_host)
        return

    try:
        status = jp2_zip_test(ia_host, ia_path, item_id)
    except socket.error:
        print 'socket error:', ia_host
        bad_hosts.add(ia_host)
        return
    if status in (403, 404):
        print 'jp2 not found:', (ol, item_id)
        return

    try:
        (cover, title) = find_title_leaf_et(ia_host, ia_path, url)
    except (KeyboardInterrupt, SystemExit, NameError):
        raise
    if not cover or not title:
        return
#    except:
#        print 'skip error:', ol, item_id, ia_host, ia_path
#        return
    print (ol, item_id, ia_host, ia_path, cover, title)
    post(ol, item_id, ia_host, ia_path, cover, title)

def has_cover_retry(key):
    for attempt in range(5):
        try:
            return has_cover(key)
        except KeyboardInterrupt:
            raise
        except:
            pass
        sleep(2)

skip = True
skip = False
for line in open('/1/edward/jsondump/2009-07-29/has_ocaid'):
    key = line[:-1]
    if key == '/b/OL6539962M': # the end
        break
    if skip:
        if key == '/b/OL6539962M':
            skip = False
        else:
            continue
    if not has_cover_retry(key):
        print 'no cover'
        continue
    print key
    e = withKey(key)
    if not e.get('ocaid', None):
        print 'no ocaid'
        continue
    find_img(e['ocaid'].strip())

fh_log.close()

print 'finished'
