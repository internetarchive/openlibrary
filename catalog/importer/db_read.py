import web
import simplejson as json
from urllib import urlopen, urlencode
from time import sleep
from catalog.read_rc import read_rc

staging = False

db = web.database(dbn='postgres', db='marc_index')
db.printing = False

def find_author(name): # unused
    iter = web.query('select key from thing, author_str where thing_id = id and key_id = 1 and value = $name', {'name': name })
    return [row.key for row in iter]

def read_from_url(url):
    for i in range(50):
        try:
            data = urlopen(url).read()
            if data:
                break
            print 'data == None'
        except IOError:
            print 'IOError'
    try:
        ret = json.loads(data)
    except:
        open('error.html', 'w').write(data)
        raise
    if ret['status'] == 'fail' and ret['message'].startswith('Not Found: '):
        return None
    assert ret['status'] == 'ok'
    return ret['result']
    for i in range(50):
        data = urlopen(url).read()
        ret = json.loads(data)
        if ret['status'] == 'ok':
            return ret['result']
        sleep(10)
    return None

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
    return read_from_url(api_get() + key)
