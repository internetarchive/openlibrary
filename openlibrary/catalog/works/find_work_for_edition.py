# try and find an existing work for a book

from openlibrary.api import OpenLibrary
from openlibrary.catalog.utils import mk_norm
import sys
from time import time

ol = OpenLibrary("http://openlibrary.org")

def find_matching_work(e):
    norm_title = mk_norm(e['title'])

    seen = set()
    for akey in e['authors']:
        q = {
            'type':'/type/work',
            'authors': {'author': {'key': akey}},
            'limit': 0,
            'title': None,
        }
        t0 = time()
        work_keys = list(ol.query(q))
        t1 = time() - t0
        print 'time to find books by author: %.1f seconds' % t1
        for w in work_keys:
            wkey = w['key']
            if wkey in seen:
                continue
            seen.add(wkey)
            if not w.get('title'):
                continue
            if mk_norm(w['title']) == norm_title:
                assert ol.query({'key': wkey, 'type': None})[0]['type'] == '/type/work'
                return wkey

def test_book():
    ekey = '/books/OL24335218M'
    wkey = find_matching_work(e)
    if wkey:
        print 'found match:', wkey
    else:
        print 'no match'
