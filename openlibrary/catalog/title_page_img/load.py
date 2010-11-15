from openlibrary.catalog.ia.scan_img import find_img
from openlibrary.catalog.utils.query import has_cover_retry
from openlibrary.catalog.read_rc import read_rc
from openlibrary.api import OpenLibrary
import web, urllib, socket, httplib, json

rc = read_rc()
ol = OpenLibrary("http://upstream.openlibrary.org/")
ol.login('ImportBot', rc['ImportBot']) 

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
        if cover is None:
            return
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

def add_cover_image(ekey, ia):
#    if has_cover_retry(key):
#        print key, 'has_cover'
#        return
    h1 = httplib.HTTPConnection('openlibrary.org')
    body = json.dumps(dict(username='ImportBot', password=rc['ImportBot']))
    headers = {'Content-Type': 'application/json'}  
    h1.request('POST', 'http://openlibrary.org/account/login', body, headers)

    res = h1.getresponse()

    res.read()
    assert res.status == 200
    cookies = res.getheader('set-cookie').split(',')
    cookie =  ';'.join([c.split(';')[0] for c in cookies])
    #print 'cookie:', cookie

    cover_url = 'http://www.archive.org/download/' + ia + '/page/' + ia + '_preview.jpg'
    body = urllib.urlencode({"url": cover_url})
    assert ekey.startswith('/books/')
    add_cover_url = 'http://openlibrary.org' + ekey + '/add-cover.json'
    #print cover_url
    #print add_cover_url
    h1.request('POST', add_cover_url, body, {'Cookie': cookie})
    res = h1.getresponse()
    res.read()
    return

    ret = find_img(ia)

    if not ret:
        return
    print 'cover image:', ret
    post(ekey, ia, ret)

def test_load():
    key = '/b/OL6544096M'
    ia = 'cu31924000331631'
    add_cover_image(key, ia)
