import simplejson
import urllib
import os
import sys
import datetime

#base_url = "http://openlibrary.org/api"
base_url = "http://pharosdb:7070/openlibrary.org"

def wget(url):
    #print url
    return urllib.urlopen(url).read()

def things(query):
    if 'limit' not in query:
        query = dict(query, limit=1000)

    _query = simplejson.dumps(query)
    result = wget(base_url + '/things?' + urllib.urlencode(dict(query=_query)))
    result = simplejson.loads(result)['result']

    if len(result) < 1000:
        return result
    else:
        return result + things(dict(query, offset=query.get('offset', 0) + 1000))
    
def get_many(keys):
    def f(keys):
        keys = simplejson.dumps(keys)
        result = wget(base_url + '/get_many?' + urllib.urlencode(dict(keys=keys)))
        return simplejson.loads(result)['result']

    d = {}
    while keys:
        d.update(f(keys[:100]))
        keys = keys[100:]
    return d

def versions(query):
    query = simplejson.dumps(query)
    result = wget(base_url + '/versions?' + urllib.urlencode(dict(query=query)))
    return simplejson.loads(result)['result']

def write(path, data):
    print 'writing', path
    dir = os.path.dirname(path)
    if dir and not os.path.exists(dir):
        os.makedirs(dir)

    f = open(path, 'w')
    f.write(data)
    f.close()

def fill_reasons(records):
    """For books with status BOOK_NOT_SCANNED, fill the reasons."""
    def get_title(e):
        if 'title_prefix' in e:
            return e['title_prefix'] + ' ' + e['title']
        else:
            return e['title']

    records = [r for r in records if r['scan_status'] == 'BOOK_NOT_SCANNED']
    editions = get_many([r['edition']['key'] for r in records])

    for r in records:
        comment = versions({'key': r['key'], 'sort': '-revision', 'limit': 1})[0]['comment']
        title = get_title(editions[r['edition']['key']])
        r['comment'] = {'reason': comment, 'title': title}

def get_scan_records(last_modified):
    """Download all scan records"""
    q = {'type': '/type/scan_record'}
    if last_modified:
        q['last_modified>'] = last_modified

    records = get_many(things(q))
    fill_reasons(records.values())

    for k, r in records.items():
        write('data' + k + '.json', simplejson.dumps(r))

def main():
    t = datetime.datetime.utcnow().isoformat()

    if os.path.exists('last_updated.txt'):
        last_updated = open('last_updated.txt').read().strip()
    else:
        last_updated = None

    get_scan_records(last_updated)
    write('last_updated.txt', t)

if __name__ == "__main__":
    main()
