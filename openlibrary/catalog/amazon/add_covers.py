from urllib2 import urlopen
import simplejson

base = 'http://ia331526.us.archive.org:7001/openlibrary.org/log/'

out = open('edition_and_isbn', 'w')
offset = '2009-06-01:0'
while not offset.startswith('2010-03-17:'):
    url = base + offset
    ret = simplejson.load(urlopen(url))
    offset, data = ret['offset'], ret['data']
    print offset, len(data)
    for i in data:
        action = i.pop('action')
        key = i['data'].pop('key', None)
        if action == 'new_account':
            continue
        author = i['data'].get('author', None) if 'data' in i else None
        if author != '/user/ImportBot':
            continue
        assert action in ('save_many', 'save')
        if action == 'save' and key.startswith('/b/'):
            e = i['data']['query']
            if e:
                isbn = e.get('isbn_10', None)
                if isbn:
                    print >> out, (key, isbn)
        elif action == 'save_many':
            for e in i['data']['query']:
                if e['type'] == '/type/edition' and e['key'].startswith('/b/'):
                    isbn = e.get('isbn_10', None)
                    if isbn:
                        print >> out, (e['key'], isbn)
out.close()
