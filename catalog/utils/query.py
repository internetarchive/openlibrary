import urllib
import simplejson as json

staging = False

def base_url():
    url = "http://0.0.0.0"
    if staging:
        url += ":8080"
    return url

def query_url():
    return base_url() + "/query.json?query="

def set_staging(i):
    global staging
    staging = i

def query(q):
    url = query_url() + urllib.quote(json.dumps(q))
    for i in range(5):
        try:
            ret = urllib.urlopen(url).read()
            while ret.startswith('canceling statement due to statement timeout'):
                ret = urllib.urlopen(url).read()
            break
        except IOError:
            pass
    try:
        return json.loads(ret)
    except:
        print ret
        print url
        raise

def query_iter(q, limit=500, offset=0):
    q['limit'] = limit
    q['offset'] = offset
    while 1:
        ret = query(q)
        if not ret:
            return
        for i in query(q):
            yield i
        q['offset'] += limit

def withKey(key):
    ret = urllib.urlopen(base_url() + key + '.json').read()
    return json.loads(ret)


