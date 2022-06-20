import sys
import re
import os
from openlibrary.catalog.parse import read_edition
from lxml.html import fromstring
import openlibrary.catalog.importer.pool as pool
from openlibrary.catalog.importer.db_read import get_mc, withKey
import openlibrary.catalog.merge.amazon as amazon_merge
from openlibrary.catalog.get_ia import (  # type: ignore[attr-defined]
    get_from_local, get_ia
)
from openlibrary.catalog.merge.merge_marc import build_marc
import openlibrary.catalog.marc.fast_parse as fast_parse

import urllib


re_amazon = re.compile(r'^([A-Z0-9]{10}),(\d+):(.*)$', re.S)

re_normalize = re.compile(r'[^\w ]')
re_whitespace = re.compile(r'\s+')
re_title_parens = re.compile(r'^(.+) \([^)]+?\)$')

re_meta_marc = re.compile(r'([^/]+)_(meta|marc)\.(mrc|xml)')
# marc:marc_ithaca_college/ic_marc.mrc:224977427:1064

threshold = 875


def normalize_str(s):
    s = re_normalize.sub('', s.strip())
    s = re_whitespace.sub(' ', s)
    return str(s.lower())


# isbn, short title
def build_index_fields(asin, edition):
    title = edition['title']
    if 'subtitle' in edition:
        title += ' ' + edition['subtitle']

    def norm(s):
        return normalize_str(s)[:25].rstrip()

    titles = {norm(title)}
    m = re_title_parens.match(title)
    if m:
        titles.add(norm(m.group(1)))

    isbn = {asin}
    for field in 'asin', 'isbn_10', 'isbn_13':
        if field in edition:
            isbn.add(edition[field].replace('-', ''))
    return {'title': list(titles), 'isbn': list(isbn)}


def read_amazon_file(f):
    while True:
        buf = f.read(1024)
        if not buf:
            break
        m = re_amazon.match(buf)
        (asin, page_len, page) = m.groups()
        page += f.read(int(page_len) - len(page))
        try:
            edition = read_edition(fromstring(page))
        except:
            print('bad record:', asin)
            raise
        if not edition:
            continue
        yield asin, edition


def follow_redirects(key):
    keys = []
    thing = None
    while not thing or thing['type']['key'] == '/type/redirect':
        keys.append(key)
        thing = withKey(key)
        assert thing
        if thing['type']['key'] == '/type/redirect':
            print('following redirect {} => {}'.format(key, thing['location']))
            key = thing['location']
    return (keys, thing)


def ia_match(a, ia):
    try:
        loc, rec = get_ia(ia)
    except urllib.error.HTTPError:
        return False
    if rec is None or 'full_title' not in rec:
        return False
    try:
        e1 = build_marc(rec)
    except TypeError:
        print(rec)
        raise
    return amazon_merge.attempt_merge(a, e1, threshold, debug=False)


def marc_match(a, loc):
    assert loc
    rec = fast_parse.read_edition(get_from_local(loc))
    e1 = build_marc(rec)
    # print 'amazon:', a
    return amazon_merge.attempt_merge(a, e1, threshold, debug=False)


def source_records_match(a, thing):
    marc = 'marc:'
    amazon = 'amazon:'
    ia = 'ia:'
    match = False
    for src in thing['source_records']:
        if not src.startswith('marc:marc_ithaca_college/ic'):
            m = re_meta_marc.search(src)
            if m:
                src = 'ia:' + m.group(1)
        if src.startswith(marc):
            if marc_match(a, src[len(marc) :]):
                match = True
                break
        elif src.startswith(ia):
            if src == 'ia:ic':
                print(thing['source_records'])
            if ia_match(a, src[len(ia) :]):
                match = True
                break
        else:
            assert src.startswith(amazon)
            continue
    return match


def try_merge(edition, ekey, thing):
    thing_type = thing['type']['key']
    if 'isbn_10' not in edition:
        print(edition)
    asin = edition.get('isbn_10', None) or edition['asin']
    if 'authors' in edition:
        authors = [i['name'] for i in edition['authors']]
    else:
        authors = []
    a = amazon_merge.build_amazon(edition, authors)
    assert isinstance(asin, str)
    assert thing_type == '/type/edition'
    # print edition['asin'], ekey
    if 'source_records' in thing:
        if 'amazon:' + asin in thing['source_records']:
            return True
        return source_records_match(a, thing)

    # print 'no source records'
    mc = get_mc(ekey)
    # print 'mc:', mc
    if mc == 'amazon:' + asin:
        return True
    if not mc:
        return False
    data = get_from_local(mc)
    e1 = build_marc(fast_parse.read_edition(data))
    return amazon_merge.attempt_merge(a, e1, threshold, debug=False)


def import_file(filename):
    for asin, edition in read_amazon_file(open(filename)):
        index_fields = build_index_fields(asin, edition)
        found = pool.build(index_fields)
        if 'title' not in found:
            print(found)
            print(asin)
            print(edition)
            print(index_fields)
            print()

        if not found['title'] and not found['isbn']:
            # print 'no pool load book:', asin
            # TODO load book
            continue
        # print asin, found
        # print(repr(edition['title'], edition.get('subtitle', None), edition.get('flags', None), edition.get('binding', None)))
        if 'sims' in edition:
            del edition['sims']
        # print edition
        # print

        seen = set()
        for k, v in found.items():
            for ekey in v:
                if ekey in seen:
                    continue
                keys, thing = follow_redirects(ekey)
                seen.update(keys)
                assert thing
                try:
                    m = try_merge(edition, ekey, thing)
                except:
                    print(asin)
                    print(edition)
                    print(ekey)
                    print(found)
                    raise


# import_file(sys.argv[1])

d = sys.argv[1]
for f in os.listdir(d):
    if not f.startswith('amazon.'):
        continue
    print(f)
    if '2009-02' in f:
        continue
    import_file(d + "/" + f)
