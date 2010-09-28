import sys, codecs
from openlibrary.catalog.utils.query import query_iter, set_staging, query
from openlibrary.api import OpenLibrary, Reference
from openlibrary.catalog.read_rc import read_rc
from time import sleep

set_staging(True)
rc = read_rc()

ol = OpenLibrary("http://dev.openlibrary.org")
ol.login('EdwardBot', rc['EdwardBot'])
sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

work_q = {
    'type': '/type/work',
    'authors': None,
    'title': None,
}

queue = []

for w in query_iter(work_q):
    if not w.get('authors'):
        print 'no authors'
        continue
    if any(isinstance(a, dict) and 'author' in a for a in w['authors']):
        continue
    print len(queue), w['key'], w['title'] # , ol.get(w['authors'][0]['key'])['name']
    full = ol.get(w['key'])
    authors = full['authors']
    assert all(isinstance(a, Reference) for a in authors)
    full['authors'] = [{'author':a} for a in authors]
    queue.append(full)
    if len(queue) > 1000:
        print 'saving'
        print ol.save_many(queue, 'update format of authors in works to provide roles')
        queue = []
        print 'two second pause'
        sleep(2)
    continue
    work_e = {
        'type': '/type/edition',
        'works': w['key'],
        'by_statement': None,
    }
    for e in query_iter(work_e):
        by = e['by_statement']
        if by:
            print '  ', e['key'], by

print 'saving'
print ol.save_many(queue, 'update format of authors in works to provide roles')

