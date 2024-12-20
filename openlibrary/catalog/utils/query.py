import json
import sys
import urllib
from time import sleep

import requests
import web

query_host = 'openlibrary.org'


def urlopen(url, data=None):
    version = "%s.%s.%s" % sys.version_info[:3]
    user_agent = f'Mozilla/5.0 (openlibrary; {__name__}) Python/{version}'
    headers = {'User-Agent': user_agent}

    return requests.get(url, data=data, headers=headers)


def jsonload(url):
    return urlopen(url).json()


def urlread(url):
    return urlopen(url).content


def set_query_host(host):
    global query_host
    query_host = host


def has_cover(key):
    url = 'https://covers.openlibrary.org/' + key[1] + '/query?olid=' + key[3:]
    return urlread(url).strip() != '[]'


def has_cover_retry(key):
    for attempt in range(5):
        try:
            return has_cover(key)
        except KeyboardInterrupt:
            raise
        except:
            pass
        sleep(2)


def base_url():
    return "http://" + query_host


def query_url():
    return base_url() + "/query.json?query="


def get_all_ia():
    print('c')
    q = {'source_records~': 'ia:*', 'type': '/type/edition'}
    limit = 10
    q['limit'] = limit
    q['offset'] = 0

    while True:
        url = base_url() + "/api/things?query=" + web.urlquote(json.dumps(q))
        ret = jsonload(url)['result']
        yield from ret
        if not ret:
            return
        q['offset'] += limit


def query(q):
    url = query_url() + urllib.parse.quote(json.dumps(q))
    ret = None
    for i in range(20):
        try:
            ret = urlread(url)
            while ret.startswith(b'canceling statement due to statement timeout'):
                ret = urlread(url)
            if not ret:
                print('ret == None')
        except OSError:
            pass
        if ret:
            try:
                data = json.loads(ret)
                if isinstance(data, dict):
                    if 'error' in data:
                        print('error:')
                        print(ret)
                    assert 'error' not in data
                return data
            except:
                print(ret)
                print(url)
        sleep(20)


def query_iter(q, limit=500, offset=0):
    q['limit'] = limit
    q['offset'] = offset
    while True:
        ret = query(q)
        if not ret:
            return
        yield from ret
        # We haven't got as many we have requested. No point making one more request
        if len(ret) < limit:
            break
        q['offset'] += limit


def get_editions_with_covers_by_author(author, count):
    q = {
        'type': '/type/edition',
        'title_prefix': None,
        'subtitle': None,
        'title': None,
        'authors': author,
    }
    with_covers = []
    for e in query_iter(q, limit=count):
        if not has_cover(e['key']):
            continue
        with_covers.append(e)
        if len(with_covers) == count:
            return with_covers
    return with_covers


def version_iter(q, limit=500, offset=0):
    q['limit'] = limit
    q['offset'] = offset
    while True:
        url = base_url() + '/version'
        v = jsonload(url)
        if not v:
            return
        yield from query(q)
        q['offset'] += limit


def withKey(key):
    url = base_url() + key + '.json'
    for i in range(20):
        try:
            return jsonload(url)
        except:
            pass
        print('retry:', i)
        print(url)


def get_marc_src(e):
    mc = get_mc(e['key'])
    if mc:
        yield mc
    if not e.get('source_records', []):
        return
    for src in e['source_records']:
        if src.startswith('marc:') and src != 'marc:' + mc:
            yield src[5:]


def get_mc(key):  # get machine comment
    v = jsonload(base_url() + key + '.json?m=history')

    comments = [
        i['machine_comment']
        for i in v
        if i.get('machine_comment', None) and ':' in i['machine_comment']
    ]
    if len(comments) == 0:
        return None
    if len(set(comments)) != 1:
        print(key)
        print(comments)
    assert len(set(comments)) == 1
    if comments[0] == 'initial import':
        return None
    return comments[0]
