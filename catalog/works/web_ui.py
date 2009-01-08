import web, re
from time import time
from catalog.read_rc import read_rc
from catalog.infostore import get_site
#from catalog.db_read import get_things, withKey
from pprint import pprint
from catalog.amazon.other_editions import find_others
from catalog.merge.normalize import normalize

rc = read_rc()

re_translation_of = re.compile('^Translation of\b[: ]*([^\n]*?)\.?$', re.I | re.M)

site = get_site()

def isbn_link(i):
    return '<a href="http://wiki-beta.us.archive.org:8081/?isbn=%s">%s</a> (<a href="http://amazon.com/dp/%s">Amazon.com</a>)' % (i, i, i)

def ol_link(key):
    return '<a href="http://openlibrary.org%s">%s</a></td>' % (key, key)

def get_author_keys(name):
    authors = site.things({ 'type': '/type/author', 'name': name })
    if authors:
        return ','.join("'%s'" % a for a in authors)
    else:
        return None

def get_title_to_key(author):
    # get id to key mapping of all editions by author
    author_keys = get_author_keys(author)
    if not author_keys:
        return {}

    # get title to key mapping of all editions by author
    t0 = time()
    sql = "select key, value as title from thing, edition_str " \
        + "where thing.id = thing_id and key_id=3 and thing_id in (" \
        + "select thing_id from edition_ref, thing " \
        + "where edition_ref.key_id=11 and edition_ref.value = thing.id and thing.key in (" + author_keys + "))"
    print sql
    return {}
    title_to_key = {}
    for r in web.query(sql):
        t = normalize(r.title).strip('.')
        title_to_key.setdefault(t, []).append(r.key)
    return title_to_key

def search(title, author):

    title_to_key = get_title_to_key(author)
    norm_title = normalize(title).strip('.')

    if norm_title not in title_to_key:
        print 'title not found'
        return

    pool = set(title_to_key[norm_title])

    editions = []
    seen = set()
    found_titles = {}
    found_isbn = {}
    while pool:
        key = pool.pop()
        seen.add(key)
        e = site.withKey(key)
        translation_of = None
        if False and e.notes:
            m = re_translation_of.search(e.notes)
            if m:
                translation_of = m.group(1).lower()
                pool.update(k for k in title_to_key[translation_of] if k not in seen)
                found_titles.setdefault(translation_of, []).append(key)
        if False and e.isbn_10:
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

urls = (
    '/', 'index'
)

def textbox(name, input):
    if name in input:
        return '<input type="text" name="%s" value="%s" size="60">' % (name, web.htmlquote(input[name]))
    else:
        return '<input type="text" name="%s" size="60">' % (name)

class index:
    def GET(self):
        web.header('Content-Type','text/html; charset=utf-8', unique=True)
        input = web.input()
        title = None
        author = None
        if 'title' in input:
            title = input.title
        if 'author' in input:
            author = input.author
        html_title = 'Work finder'
        print "<html>\n<head>\n<title>%s</title>" % html_title
        print '''
<style>
th { text-align: left }
td { padding: 5px; background: #eee }
</style>'''

        print '</head><body><a name="top">'

        print "<body><html>"
        print '<form name="main" method="get">'
        print '<table><tr><td align="right">Title</td>',
        print '<td>', textbox('title', input), '</td></tr>'
        print '<tr><td align="right">Author</td>'
        print '<td>', textbox('author', input), '</td></tr>'
        print '<tr><td></td><td><input type="submit" value="find"></td></tr>'
        print '</table>'
        if title and author:
            search(title, author)
        print '</form>'

if __name__ == "__main__": web.run(urls, globals(), web.reloader)
