import web, cjson
from urllib import urlopen, urlencode
from time import sleep
import catalog.infostore

staging = False

def find_author(name):
    iter = web.query('select key from thing, author_str where thing_id = id and key_id = 1 and value = $name', {'name': name })
    return [row.key for row in iter]

def read_from_url(url):
    for i in range(50):
        data = urlopen(url).read()
        try:
            ret = cjson.decode(data)
            if ret['status'] == 'ok':
                return ret['result']
        except cjson.DecodeError:
            pass
        sleep(10)
    print url
    print data
    return None

def set_staging(v):
    global staging
    staging = v

def api_url():
    return "http://openlibrary.org%s/api/" % (':8080' if staging else '')
    
def api_versions(): return api_url() + "versions?"
def api_things(): return api_url() + "things?"
def api_get(): return api_url() + "get?key="

def get_versions(q):
    url = api_versions() + urlencode({'query': cjson.encode(q)})
    return read_from_url(url)

def get_things(q):
    url = api_things() + urlencode({'query': cjson.encode(q)})
    return [i.replace('\/', '/') for i in read_from_url(url)]

def get_mc(edition_key):
    v = get_versions({ 'key': edition_key })
    comments = [i['machine_comment'] for i in v if 'machine_comment' in i and i['machine_comment'] is not None ]
    if len(comments) == 0:
        return None
    if len(set(comments)) != 1:
        print id
        print versions
    assert len(set(comments)) == 1
    if comments[0] == 'initial import':
        return None
    return comments[0]

def withKey(key):
    return read_from_url(api_get() + key)


