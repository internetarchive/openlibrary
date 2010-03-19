from urllib2 import urlopen
import simplejson
from time import time, sleep
from openlibrary.catalog.utils.query import withKey, query_iter
from openlibrary.solr.update_work import update_work, solr_update, update_author, AuthorRedirect
from openlibrary.api import OpenLibrary, Reference
from openlibrary.catalog.read_rc import read_rc

rc = read_rc()
ol = OpenLibrary("http://openlibrary.org")
ol.login('EdwardBot', rc['EdwardBot']) 

base = 'http://ia331526.us.archive.org:7001/openlibrary.org/log/'

state_file = rc['state_dir'] + '/solr_update'
offset = open(state_file).readline()[:-1]

print 'start:', offset
authors_to_update = set()
works_to_update = set()
last_update = time()

def run_update():
    global authors_to_update
    global works_to_update
    global last_update
    last_update = time()
    print 'running update: %s works %s authors' % (len(works_to_update), len(authors_to_update))
    if works_to_update:
        requests = []
        num = 0
        total = len(works_to_update)
        for wkey in works_to_update:
            num += 1
            print 'update work: %s %d/%d' % (wkey, num, total)
            if '/' in wkey[7:]:
                print 'bad wkey:', wkey
                continue
            for attempt in range(5):
                try:
                    requests += update_work(withKey(wkey))
                    break
                except AuthorRedirect:
                    print 'fixing author redirect'
                    w = ol.get(wkey)
                    need_update = False
                    for a in w['authors']:
                        r = ol.get(a['author'])
                        if r['type'] == '/type/redirect':
                            a['author'] = Reference(r['location'])
                            need_update = True
                    assert need_update
                    ol.save(w['key'], w, 'avoid author redirect')

        solr_update(requests + ['<commit/>'], debug=True)
    if authors_to_update:
        requests = []
        for akey in authors_to_update:
            print 'update author:', akey
            requests += update_author(akey)
        solr_update(requests + ['<commit/>'], index='authors', debug=True)
    authors_to_update = set()
    works_to_update = set()
    print >> open(statefile, 'w'), offset

while True:
    url = base + offset
    ret = simplejson.load(urlopen(url))
    offset = ret['offset']
    data = ret['data']
    print offset, len(data), '%s works %s authors' % (len(works_to_update), len(authors_to_update))
    if len(data) == 0:
        if authors_to_update or works_to_update:
            run_update()
        sleep(5)
        continue
    for i in data:
        action = i.pop('action')
        key = i['data'].pop('key', None)
        if key and key.startswith('/upstream'):
            continue
        if action == 'new_account':
            continue
        author = i['data'].get('author', None) if 'data' in i else None
        if author in ('/user/ImportBot', '/user/WorkBot', '/user/AccountBot'):
            if action not in ('save', 'save_many'):
                print action, author, key, i.keys()
                print i['data']
            assert action in ('save', 'save_many')
            continue
        if action == 'save' and key.startswith('/a/'):
            authors_to_update.add(key)
            q = {'type':'/type/work', 'authors':{'author':key}}
            works_to_update.update(w['key'] for w in query_iter(q))
        elif action == 'save' and key.startswith('/works/'):
            works_to_update.add(key)
            print i
            query = i['data']['query']
            if query:
                authors_to_update.update(a['author'] for a in query.get('authors', []) if a.get('author', None))
        elif action == 'save' and key.startswith('/b/') and i['data']['query']:
            query = i['data']['query']
            if query['type'] != '/type/edition':
                print 'bad type for ', key
                continue
            works_to_update.update(query.get('works', []))
            try:
                authors_to_update.update(query.get('authors', []))
            except:
                print query
                raise
        elif action == 'save' and key.startswith('/user/'):
            pass
        else:
            pass
    since_last_update = time() - last_update
    if len(works_to_update) > 500 or len(authors_to_update) > 500 or since_last_update > 60 * 30:
        run_update()

