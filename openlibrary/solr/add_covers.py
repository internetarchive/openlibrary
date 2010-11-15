from openlibrary.api import OpenLibrary, Reference
from openlibrary.catalog.utils.query import query_iter, withKey
from openlibrary.catalog.read_rc import read_rc
import re

ol = None
edition_covers = None

re_year = re.compile('(\d{4})$')

def add_cover_to_work(w):
    if 'cover_edition' in w:
        return
    q = {'type':'/type/edition', 'works':w['key'], 'publish_date': None, 'languages': '/l/eng'}
    cover_edition = pick_cover(query_iter(q))
    if not cover_edition:
        q = {'type':'/type/edition', 'works':w['key'], 'publish_date': None}
        cover_edition = pick_cover(query_iter(q))
        if not cover_edition:
            return
    w['cover_edition'] = Reference(cover_edition)
    if ol is None:
        rc = read_rc()
        ol = OpenLibrary("http://openlibrary.org")
        ol.login('WorkBot', rc['WorkBot']) 

    print ol.save(w['key'], w, 'added cover to work')

def get_covers(editions):
    global edition_covers
    for e in editions:
        pub_date = e.get('publish_date', None)
        if edition_covers is None:
            edition_covers = set(line[:-1] for line in open('/home/edward/scratch/editions_with_covers'))
        if not pub_date or e['key'][3:] not in edition_covers:
            continue
        m = re_year.search(pub_date.strip())
        if not m:
            print 'year not found:', `pub_date`
            continue
        pub_year = m.group(1)
        yield pub_year, e['key']

def pick_cover(editions):
    for pub_year, ekey in sorted(get_covers(editions), reverse=True):
        e = withKey(ekey)
        if e['type']['key'] == '/type/edition':
            return ekey
