import urllib, web
import simplejson as json
from time import sleep

staging = False

def base_url():
    host = 'openlibrary.org'
    if staging:
        host = 'dev.' + host
    return "http://" + host

def query_url():
    return base_url() + "/query.json?query="

def get_all_ia():
    print 'c'
    q = {'source_records~': 'ia:*', 'type': '/type/edition'}
    limit = 10
    q['limit'] = limit
    q['offset'] = 0

    while True:
        url = base_url() + "/api/things?query=" + web.urlquote(json.dumps(q))
        ret = json.load(urllib.urlopen(url))['result']
        for i in ret:
            yield i
        if not ret:
            return
        q['offset'] += limit

def set_staging(i):
    global staging
    staging = i

def query(q):
    url = query_url() + urllib.quote(json.dumps(q))
    ret = None
    for i in range(20):
        try:
            ret = urllib.urlopen(url).read()
            while ret.startswith('canceling statement due to statement timeout'):
                ret = urllib.urlopen(url).read()
            if not ret:
                print 'ret == None'
        except IOError:
            pass
        if ret:
            try:
                return json.loads(ret)
            except:
                print ret
                print url
        sleep(20)

def query_iter(q, limit=500, offset=0):
    q['limit'] = limit
    q['offset'] = offset
    while True:
        ret = query(q)
        if not ret:
            return
        for i in ret:
            yield i
        q['offset'] += limit

def version_iter(q, limit=500, offset=0):
    q['limit'] = limit
    q['offset'] = offset
    while True:
        url = base_url() + '/version'
        v = json.load(urllib.urlopen(url))
        if not v:
            return
        for i in query(q):
            yield i
        q['offset'] += limit

def withKey(key):
    for i in range(20):
        try:
            ret = urllib.urlopen(base_url() + key + '.json').read()
            return json.loads(ret)
        except:
            pass
        print 'retry'
        sleep(10)

def get_marc_src(e):
    mc = get_mc(e['key'])
    if mc:
        yield mc
    if not e.get('source_records', []):
        return
    for src in e['source_records']:
        if src.startswith('marc:') and src != 'marc:' + mc:
            yield src[5:]

def get_mc(key): # get machine comment
    url = base_url() + key + '.json?m=history'
    ret = urllib.urlopen(url).read()
    v = json.loads(ret)

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

    return 'mc'
