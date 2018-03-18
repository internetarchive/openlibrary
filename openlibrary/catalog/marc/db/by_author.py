#!/usr/bin/python2.5
import web, re
from catalog.utils.query import query_iter, withKey
from web_marc_db import search_query, marc_data, esc
from catalog.marc.fast_parse import get_all_subfields, get_tag_lines, get_first_tag, get_subfields
from catalog.utils import pick_first_date, flip_name, author_dates_match
from collections import defaultdict

urls = (
    '/', 'index'
)

def read_line(line, name):
    if not line or '\x1fd' not in line:
        return
    subfields = tuple((k, v.strip(' /,;:')) for k, v in get_subfields(line, 'abcd'))
    marc_name = ' '.join(v for k, v in subfields if k in 'abc')
    flipped = flip_name(marc_name)
    if marc_name != name and flipped != name:
        return
    d = pick_first_date(v for k, v in subfields if k in 'abcd')
    dates = tuple(d.get(k, None) for k in ['birth_date', 'death_date', 'date'])
    return (marc_name, flipped, dates)

def data_from_marc(locs, name):
    lines = defaultdict(list)
    for loc in locs:
        data = marc_data(loc)
        line = read_line(get_first_tag(data, set(['100'])), name)
        if line:
            lines[line].append(loc)
        for tag, line in get_tag_lines(data, set(['700'])):
            line = read_line(line, name)
            if line:
                lines[line].append(loc)
    return lines

def author_search(name):
    q = {
        'type':'/type/author',
        'name': name,
        'birth_date': None,
        'death_date': None,
        'dates': None
    }
    return [a for a in query_iter(q) if a.get('birth_date', None) or a.get('death_date', None) or a.get('dates', None)]

def search(author, name):
    book_fields = ('title_prefix', 'title');
    q = { 'type': '/type/edition', 'authors': author, 'title_prefix': None, 'title': None, 'isbn_10': None}
    found = list(query_iter(q))
    db_author = ''
    names = set([name])
    t = ''
    books = []
    for e in found:
        locs = set()
        for i in e['isbn_10'] or []:
            locs.update(search_query('isbn', i))
        if not locs:
            books.append((e['key'], (e['title_prefix'] or '') + e['title'], None, []))
            continue
        found = data_from_marc(locs, name)
        if len(found) != 1:
            locs = []
            for i in found.values():
                locs.append(i)
            books.append((e['key'], (e['title_prefix'] or '') + e['title'], None, locs))
            continue
        marc_author = found.keys()[0]
        locs = found.values()[0]
        names.update(marc_author[0:2])
        books.append((e['key'], (e['title_prefix'] or '') + e['title'], marc_author, locs))

    authors = []
    names2 = set()
    for n in names:
        if ', ' in n:
            continue
        i = n.rfind(' ')
        names2.add("%s, %s" % (n[i+1:], n[:i]))
    names.update(names2)

    for n in names:
        for a in author_search(n):
            authors.append(a)

    for a in authors:
        q = {
            'type': '/type/edition',
            'authors': a['key'],
            'title_prefix': None,
            'title': None,
            'isbn_10': None
        }
        a['editions'] = list(query_iter(q))

    author_map = {}

    for key, title, a, locs in books:
        t += '<tr><td><a href="http://openlibrary.org' + key + '">' + web.htmlquote(title) + '</a>'
        t += '<br>' + ', '.join('<a href="http://openlibrary.org/show-marc/%s">%s</a>' % (i, i) for i in locs) + '</td>'
#        t += '<td>' + web.htmlquote(repr(a[2])) + '</td>'
        if a:
            if a[2] not in author_map:
                dates = {'birth_date': a[2][0], 'death_date': a[2][1], 'dates': a[2][2]}
                db_match = [db for db in authors if author_dates_match(dates, db)]
                author_map[a[2]] = db_match[0] if len(db_match) == 1 else None

            match = author_map[a[2]]
            if match:
                t += '<td><a href="http://openlibrary.org%s">%s-%s</a></td>' % (match['key'], match['birth_date'] or '', match['death_date'] or '')
            else:
                t += '<td>%s-%s (no match)</td>' % (dates['birth_date'] or '', dates['death_date'] or '')
        t += '</tr>\n'

    ret = ''
    if authors:
        ret += '<ul>'
        for a in authors:
            ret += '<li><a href="http://openlibrary.org%s">%s</a> (%s-%s) %d editions' % (a['key'], web.htmlquote(name), a['birth_date'] or '', a['death_date'] or '', len(a['editions']))
        ret += '</ul>'

    return ret + '<table>' + t + '</table>'

class index():
    def GET(self):
        web.header('Content-Type','text/html; charset=utf-8', unique=True)
        input = web.input()
        title = 'Tidy author'
        if 'author' in input and input.author:
            author = input.author
            name = withKey(author)['name']
            q_name = web.htmlquote(name)
            title = q_name + ' - Tidy author'
        else:
            author = None
        ret = "<html>\n<head>\n<title>%s</title>" % title

        ret += '''
<style>
th { text-align: left }
td { padding: 5px; background: #eee }
</style>'''

        ret += '</head><body><a name="top">'
        ret += '<form name="main" method="get"><table><tr><td align="right">Author</td><td>'
        if author:
            ret += '<input type="text" name="author" value="%s">' % web.htmlquote(author)
        else:
            ret += '<input type="text" name="author">'
        ret += '</td>'
        ret += '<td><input type="submit" value="find"></td></tr>'
        ret += '</table>'
        ret += '</form>'
        if author:
            ret += 'Author: <a href="http://openlibrary.org%s">%s</a><br>' % (author, name)
            ret += search(author, name)
        ret += "</body></html>"
        return ret

app = web.application(urls, globals())

if __name__ == "__main__":
    app.run()
