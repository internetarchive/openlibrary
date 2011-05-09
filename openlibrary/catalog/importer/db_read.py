import web
import simplejson as json
from urllib import urlopen, urlencode
from time import sleep
from openlibrary.catalog.read_rc import read_rc

staging = False

db = web.database(dbn='postgres', db='marc_index', host='ol-db')
db.printing = False

def find_author(name): # unused
    iter = web.query('select key from thing, author_str where thing_id = id and key_id = 1 and value = $name', {'name': name })
    return [row.key for row in iter]

def read_from_url(url):
    data = None
    for i in range(20):
        try:
            data = urlopen(url).read()
            if data:
                break
            print 'data == None'
        except IOError:
            print 'IOError'
            print url
        sleep(10)
    if not data:
        return None
    ret = json.loads(data)
    if ret['status'] == 'fail' and ret['message'].startswith('Not Found: '):
        return None
    if ret['status'] != 'ok':
        print ret
    assert ret['status'] == 'ok'
    return ret['result']

def set_staging(v):
    global staging
    staging = v

def api_url():
    return "http://openlibrary.org%s/api/" % (':8080' if staging else '')
    
def api_versions(): return api_url() + "versions?"
def api_things(): return api_url() + "things?"
def api_get(): return api_url() + "get?key="

def get_versions(q): # unused
    url = api_versions() + urlencode({'query': json.dumps(q)})
    return read_from_url(url)

def get_things(q):
    url = api_things() + urlencode({'query': json.dumps(q)})
    return read_from_url(url)

def get_mc(key):
    found = list(db.query('select v from machine_comment where k=$key', {'key': key}))
    return found[0].v if found else None

def withKey(key):
    def process(key):
        return read_from_url(api_get() + key)

    for attempt in range(5):
        try:
            return process(key)
        except ValueError:
            pass
        sleep(10)
    return process(key)
