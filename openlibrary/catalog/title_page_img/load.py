from openlibrary.catalog.ia.scan_img import find_img
from openlibrary.catalog.utils.query import has_cover_retry
from openlibrary.catalog.read_rc import read_rc
import web, urllib, socket, httplib

def urlread(url):
    return urllib.urlopen(url).read()

def post_cover(ol, source_url):
    param = urllib.urlencode({'olid': ol[3:], 'source_url': source_url})
    headers = {"Content-type": "application/x-www-form-urlencoded"}
    conn = httplib.HTTPConnection("covers.openlibrary.org", timeout=20)
    conn.request("POST", "/b/upload", param, headers)
    r1 = conn.getresponse()
    print r1.status, r1.reason
    assert r1.status in (200, 303, 500)
    conn.close()

def post(key, ia, from_ia):
    use_cover = False
    title = from_ia['title']
    cover = from_ia['cover']
    if title is None:
        assert cover is not None
        use_cover = True
    leaf = cover if use_cover else title
    zip_type = 'tif' if ia.endswith('goog') else 'jp2'
    source_url = "http://%s/GnuBook/GnuBookImages.php?zip=%s/%s_%s.zip&file=%s_%s/%s_%04d.%s" % (from_ia['ia_host'], from_ia['ia_path'], ia, zip_type, ia, zip_type, ia, leaf, zip_type)
    query = 'http://covers.openlibrary.org/b/query?olid=' + key[3:]
    if use_cover:
        print 'use_cover',
    for attempt in range(5):
        if attempt > 0:
            print 'trying again (%d)' % attempt
        try:
            ret = urlread(query).strip()
        except IOError:
            continue
        print ret
        if ret != '[]':
            break
        try:
            post_cover(key, source_url)
        except socket.timeout:
            print 'socket timeout'
            break
        except httplib.BadStatusLine:
            print 'bad status line'
            continue
        break

def add_cover_image(key, ia):
    if has_cover_retry(key):
        print key, 'has_cover'
    ret = find_img(ia)

    print 'cover image:', ret
    post(key, ia, ret)

def test_load():
    key = '/b/OL6544096M'
    ia = 'cu31924000331631'
    add_cover_image(key, ia)
