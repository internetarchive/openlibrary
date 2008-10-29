from urllib2 import urlopen, Request
import cjson, web
import dbhash

index_path = '/1/pharos/edward/index/2/'

pool_url = 'http://wiki-beta.us.archive.org:9020/'

def build(fields):
    params = dict((k, '_'.join(v)) for k, v in fields.iteritems() if k != 'author')
    url = pool_url + "?" + web.http.urlencode(params)
    ret = cjson.decode(urlopen(url).read())
    return ret['pool']

def update(key, q):
    q['key'] = key
    req = Request(pool_url, cjson.encode(q))
    urlopen(req).read()

def post_progress(archive_id, q):
    url = pool_url + "store/" + archive_id
    req = Request(url, cjson.encode(q))
    urlopen(req).read()

def get_start(archive_id):
    url = pool_url + "store/" + archive_id
    data = urlopen(url).read()
    return cjson.decode(data)
