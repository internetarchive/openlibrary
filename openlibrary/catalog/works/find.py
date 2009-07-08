import web, re, sys
from catalog.read_rc import read_rc
from catalog.infostore import get_site
#from catalog.db_read import get_things, withKey
from pprint import pprint
from catalog.amazon.other_editions import find_others

rc = read_rc()

re_translation_of = re.compile('^Translation of\b[: ]*([^\n]*?)\.?$', re.I | re.M)

site = get_site()

def isbn_link(i):
    return '<a href="http://wiki-beta.us.archive.org:8081/?isbn=%s">%s</a> (<a href="http://amazon.com/dp/%s">Amazon.com</a>)' % (i, i, i)

def ol_link(key):
    return '<a href="http://openlibrary.org%s">%s</a></td>' % (key, key)

def search(title, author):
    q = { 'type': '/type/author', 'name': author }
    print q
    authors = site.things(q)
    print authors
    seen = set()
    pool = set()
#    for a in authors:
#        q = { 'type': '/type/edition', 'authors': a, 'title': title }
#        pool.update(site.things(q))
    found_titles = {}
    found_isbn = {}
    author_keys = ','.join("'%s'" % a for a in authors)

    print author_keys
    iter = web.query("select id, key from thing where thing.id in (select thing_id from edition_ref, thing where edition_ref.key_id=11 and edition_ref.value = thing.id and thing.key in (" + author_keys + "))")
    key_to_id = {}
    id_to_key = {}
    for row in iter:
        print row
        key_to_id[row.key] = row.id
        id_to_key[row.id] = row.key


    iter = web.query("select thing_id, edition_str.value as title from edition_str where key_id=3 and thing_id in (select thing_id from edition_ref, thing where edition_ref.key_id=11 and edition_ref.value = thing.id and thing.key in (" + author_keys + "))")
    id_to_title = {}
    title_to_key = {}
    for row in iter:
        print row
        t = row.title.lower().strip('.')
        id_to_title[row.thing_id] = row.title
        title_to_key.setdefault(t, []).append(id_to_key[row.thing_id])

    if title.lower() not in title_to_key:
        print 'title not found'
        return

    pool = set(title_to_key[title.lower()])

    editions = []
    while pool:
        key = pool.pop()
        print key
        seen.add(key)
        e = site.withKey(key)
        translation_of = None
        if e.notes:
            m = re_translation_of.search(e.notes)
            if m:
                translation_of = m.group(1).lower()
                pool.update(k for k in title_to_key[translation_of] if k not in seen)
                found_titles.setdefault(translation_of, []).append(key)
        if e.isbn_10:
            for i in e.isbn_10:
                found_isbn.setdefault(i, []).append(key)
            join_isbn = ', '.join(map(isbn_link, e.isbn_10))
        else:
            join_isbn = ''
        rec = {
            'key': key,
            'publish_date': e.publish_date,
            'publishers': ', '.join(p.encode('utf-8') for p in (e.publishers or [])),
            'isbn': join_isbn,
        }
        editions.append(rec)

        if e.work_titles:
            for t in e.work_titles:
                t=t.strip('.')
                pool.update(k for k in title_to_key.get(t.lower(), []) if k not in seen)
                found_titles.setdefault(t, []).append(key)
        if e.other_titles:
            for t in e.other_titles:
                t=t.strip('.')
                pool.update(k for k in title_to_key.get(t.lower(), []) if k not in seen)
                found_titles.setdefault(t, []).append(key)

    print '<table>'
    for e in sorted(editions, key=lambda e: e['publish_date'] and e['publish_date'][-4:]):
        print '<tr>'
        print '<td>', ol_link(e['key'])
        print '<td>', e['publish_date'], '</td><td>', e['publishers'], '</td>'
        print '<td>', e['isbn'], '</td>'
        print '</tr>'
    print '</table>'

    if found_titles:
        print '<h2>Other titles</h2>'
        print '<ul>'
        for k, v in found_titles.iteritems():
            if k == title:
                continue
            print '<li><a href="/?title=%s&author=%s">%s</a>' % (k, author, k),
            print 'from', ', '.join(ol_link(i) for i in v)
        print '</ul>'

    extra_isbn = {}
    for k, v in found_isbn.iteritems():
        for isbn, note in find_others(k, rc['amazon_other_editions']):
            if note.lower().find('audio') != -1:
                continue
            if isbn not in found_isbn:
                extra_isbn.setdefault(isbn, []).extend(v)

    if extra_isbn:
        print '<h2>Other ISBN</h2>'
        print '<ul>'
        for k in sorted(extra_isbn):
            print '<li>', isbn_link(k),
            print 'from', ', '.join(ol_link(i) for i in extra_isbn[k])
        print '</ul>'

title = 'Journey to the centre of the earth'
author = 'Jules Verne'
search(title, author)
