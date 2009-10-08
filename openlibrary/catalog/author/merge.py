# -*- coding: utf-8 -*-
from openlibrary.catalog.importer.db_read import withKey, get_things, get_mc
from openlibrary.catalog.read_rc import read_rc
from openlibrary.catalog.utils import key_int, match_with_bad_chars, pick_best_author, remove_trailing_number_dot
from unicodedata import normalize
import web, re, sys, codecs, urllib
sys.path.append('/home/edward/src/olapi')
from olapi import OpenLibrary, unmarshal
from openlibrary.catalog.utils.edit import fix_edition
from openlibrary.catalog.utils.query import query_iter

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

rc = read_rc()
ol = OpenLibrary("http://openlibrary.org")
ol.login('EdwardBot', rc['EdwardBot']) 

def urlread(url):
    return urllib.urlopen(url).read()

def norm(s):
    return normalize('NFC', s)

def copy_fields(from_author, to_author, name):
    new_fields = { 'name': name, 'personal_name': name }
    for k, v in from_author.iteritems():
        if k in ('name', 'personal_name', 'key', 'last_modified', 'type', 'id', 'revision'):
            continue
        if k in to_author:
            assert v == to_author[k]
        else:
            new_fields[k] = v
    return new_fields

def test_copy_fields():
    f = {'name': 'Sheila K. McCullagh', 'personal_name': 'Sheila K. McCullagh', 'last_modified': {'type': '/type/datetime', 'value': '2008-08-30 20:40:41.784992'}, 'key': '/a/OL4340365A', 'birth_date': '1920', 'type': {'key': '/type/author'}, 'id': 18087251, 'revision': 1}
    t = {'name': 'Sheila K. McCullagh', 'last_modified': {'type': '/type/datetime', 'value': '2008-04-29 13:35:46.87638'}, 'key': '/a/OL2622088A', 'type': {'key': '/type/author'}, 'id': 9890186, 'revision': 1}

    assert copy_fields(f, t, 'Sheila K. McCullagh') == {'birth_date': '1920', 'name': 'Sheila K. McCullagh', 'personal_name': 'Sheila K. McCullagh'}


def update_author(key, new):
    q = { 'key': key, }
    for k, v in new.iteritems():
        q[k] = { 'connect': 'update', 'value': v }
    print ol.write(q, comment='merge author')

def update_edition(key, old, new):
    print 'key:', key
    print 'old:', old
    print 'new:', new
    e = ol.get(key)
    fix_edition(key, e, ol)
    authors = []
    print 'current authors:', e['authors']
    for cur in e['authors']:
        cur = cur['key']
        print old, cur in old
        a = new if cur in old else cur
        print cur, '->', a
        if a not in authors:
            authors.append({'key': a})
    print 'authors:', authors
    e['authors'] = authors

    try:
        print ol.save(key, e, 'merge authors')
    except:
        print e
        raise
    new_edition = ol.get(key)
    if 'table_of_contents' in new_edition:
        # [{u'type': <ref: u'/type/toc_item'>}, ...]
        print key, new_edition['table_of_contents']
        #assert 'title' in new_edition['table_of_contents'][0]
#    assert all(cur not in old for cur in e['authors'])

def switch_author(old, new, other):
    q = { 'authors': old, 'type': '/type/edition', }
    for e in query_iter(q):
        print 'switch author:', e['key']
        update_edition(e['key'], other, new)

def make_redirect(old, new):
    r = {'type': {'key': '/type/redirect'}, 'location': new}
    ol.save(old, r, 'replace with redirect')

re_number_dot = re.compile('\d{2,}[- ]*(\.+)$')

def do_normalize(author_key, best_key, authors):
    #print "do_normalize(%s, %s, %s)" % (author_key, best_key, authors)
    need_update = False
    a = ol.get(author_key)
    if author_key == best_key:
        for k, v in a.items():
            if 'date' in k:
                m = re_number_dot.search(v)
                if m:
                    need_update = True
                    v = v[:-len(m.group(1))]
            if not isinstance(v, unicode):
                continue
            norm_v = norm(v)
            if v == norm_v:
                continue
            a[k] = norm_v
            need_update = True
    else:
        best = ol.get(best_key)
        author_keys = set(k for k in a.keys() + best.keys() if k not in ('key', 'last_modified', 'type', 'id', 'revision'))
        for k in author_keys:
            if k not in best:
                v = a[k]
                if not isinstance(v, unicode):
                    continue
                norm_v = norm(v)
                if v == norm_v:
                    continue
                a[k] = norm_v
                need_update = True
                continue
            v = best[k]
            if 'date' in k:
                v = remove_trailing_number_dot(v)
            if isinstance(v, unicode):
                v = norm(v)
            if k not in a or v != a[k]:
                a[k] = v
                need_update = True
    if not need_update:
        return
    #print 'save(%s, %s)' % (author_key, `a`)
    ol.save(author_key, a, 'merge authors')

def has_image(key):
    url = 'http://covers.openlibrary.org/a/query?olid=' + key[3:]
    ret = urlread(url).strip()
    return ret != '[]'

def merge_authors(keys):
#    print 'merge author %s:"%s" and %s:"%s"' % (author['key'], author['name'], merge_with['key'], merge_with['name'])
#    print 'becomes: "%s"' % `new_name`
    authors = [a for a in (withKey(k) for k in keys) if a['type']['key'] != '/type/redirect']
    not_redirect = set(a['key'] for a in authors)
    for a in authors:
        print a

    assert all(a['type']['key'] == '/type/author' for a in authors)
    name1 = authors[0]['name']
    assert all(match_with_bad_chars(a['name'], name1) for a in authors[1:])

    best_key = pick_best_author(authors)['key']

    imgs = [a['key'] for a in authors if has_image(a['key'])]
    if len(imgs) == 1:
        new_key = imgs[0]
    else:
        new_key = "/a/OL%dA" % min(key_int(a) for a in authors)
        # Molière and O. J. O. Ferreira
        if len(imgs) != 0:
            print 'imgs:', imgs
            return # skip
        if not (imgs == [u'/a/OL21848A', u'/a/OL4280680A'] \
                or imgs == [u'/a/OL325189A', u'/a/OL266422A'] \
                or imgs == [u'/a/OL5160945A', u'/a/OL5776228A']):
            print imgs
            assert len(imgs) == 0

    do_normalize(new_key, best_key, authors)
    old_keys = set(k for k in keys if k != new_key) 
    print 'old keys:', old_keys
    for old in old_keys:
        # /b/OL21291659M
        switch_author(old, new_key, old_keys)
        if old in not_redirect:
            make_redirect(old, new_key)
        q = { 'authors': old, 'type': '/type/edition', }
        if list(get_things(q)) != []:
            switch_author(old, new_key, old_keys)
        l = list(query_iter(q))
        print old, l
        assert l == []
    
if __name__ == '__main__':
    assert len(sys.argv) > 2
    merge_authors(sys.argv[1:])
