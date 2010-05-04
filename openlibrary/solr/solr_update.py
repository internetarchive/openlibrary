from urllib2 import urlopen
import simplejson
from time import time, sleep
from openlibrary.catalog.utils.query import withKey
from openlibrary.solr.update_work import update_work, solr_update, update_author, AuthorRedirect
from openlibrary.api import OpenLibrary, Reference
from openlibrary.catalog.read_rc import read_rc
from openlibrary.catalog.works.find_works import find_title_redirects, find_works, get_books, books_query, update_works

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
                            a['author'] = {'key': r['location']}
                            need_update = True
                    assert need_update
                    print w
                    ol.save(w['key'], w, 'avoid author redirect')

        solr_update(requests + ['<commit/>'], debug=True)
    print >> open(state_file, 'w'), offset
    if False and authors_to_update:
        requests = []
        for akey in authors_to_update:
            print 'update author:', akey
            requests += update_author(akey)
        solr_update(requests + ['<commit/>'], index='authors', debug=True)
    authors_to_update = set()
    works_to_update = set()
    print >> open(state_file, 'w'), offset

def process_save(key, query):
    if query:
        obj_type = query['type']['key'] if isinstance(query['type'], dict) else query['type']
        if obj_type == '/type/delete':
            print key, 'deleted'
    if key.startswith('/authors/') or key.startswith('/a/'):
        authors_to_update.add(key)
        q = {
            'type':'/type/work',
            'authors':{'author':{'key': key}}
        }
        works_to_update.update(ol.query(q))
        return
    if key.startswith('/works/'):
        works_to_update.add(key)
        if query:
            authors_to_update.update(a['author']['key'] if isinstance(a['author'], dict) else a['author'] for a in query.get('authors', []) if a.get('author', None))
        return
    if (key.startswith('/books/') or key.startswith('/b/')) and query and obj_type != '/type/delete':
        if obj_type != '/type/edition':
            print 'bad type for ', key
            return
        works_to_update.update(w['key'] if isinstance(w, dict) else w for w in query.get('works', []))
        try:
            authors_to_update.update(a['key'] if isinstance(a, dict) else a for a in query.get('authors', []))
        except:
            print query
            raise

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
        if action == 'new_account':
            continue
        author = i['data'].get('author', None) if 'data' in i else None
        if author in ('/user/AccountBot',):
            if action not in ('save', 'save_many'):
                print action, author, key, i.keys()
                print i['data']
            assert action in ('save', 'save_many')
            continue
        if action == 'save':
            key = i['data'].pop('key')
            process_save(key, i['data']['query'])
        elif action == 'save_many':
            if not i['data']['author'].endswith('Bot') and i['data']['comment'] == 'merge authors':
                first_redirect = i['data']['query'][0]
                assert first_redirect['type']['key'] == '/type/redirect'
                akey = first_redirect['location']
                if akey.startswith('/authors/'):
                    akey = '/a/' + akey[len('/authors/'):]
                title_redirects = find_title_redirects(akey)
                works = find_works(akey, get_books(akey, books_query(akey)), existing=title_redirects)
                updated = update_works(akey, works, do_updates=True)
                works_to_update.update(w['key'] for w in updated)
            for query in i['data']['query']:
                key = query.pop('key')
                process_save(key, query)
    since_last_update = time() - last_update
    if len(works_to_update) > 1000 or len(authors_to_update) > 1000 or since_last_update > 60 * 30:
        run_update()

