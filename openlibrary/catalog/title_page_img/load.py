from openlibrary.catalog.read_rc import read_rc
import urllib, httplib, json

rc = read_rc()

def add_cover_image(ekey, ia):
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
    headers = {'Content-type': 'application/x-www-form-urlencoded', 'Cookie': cookie}
    h1.request('POST', add_cover_url, body, {'Cookie': cookie})
    res = h1.getresponse()
    res.read()
    return
