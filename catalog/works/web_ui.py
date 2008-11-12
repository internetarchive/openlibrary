import web, re
from catalog.read_rc import read_rc
from catalog.infostore import get_site
#from catalog.db_read import get_things, withKey
from pprint import pprint
from catalog.amazon.other_editions import find_others

rc = read_rc()

re_translation_of = re.compile('^Translation of\b[: ]*([^\n]*)$', re.I, re.M)

site = get_site()

def search(title, author):
    q = { 'type': '/type/author', 'name': author }
    authors = site.things(q)
    pool = set()
    for a in authors:
        q = { 'type': '/type/edition', 'authors': a, 'title': title }
        pool += set(site.things(q))
    if not pool:
        return
    titles_set = set()
    isbn_set = set()
    for key in pool:
        e = site.withKey(key)
        translation_of = None
        if e.notes:
            m = re_translation_of.search(e.notes)
            if m:
                translation_of = m.group(1)
                titles.add(translation_of)
        print '<a href="http://openlibrary.org%s">%s</a>' % (key, key), \
                e.publish_date, ','.join(e.publishers), '<br>'
        if e.isbn_10:
            isbn_set += set(e.isbn_10)
        if e.work_titles:
            titles_set += set(e.work_titles)
        if e.other_titles:
            titles_set += set(e.other_titles)
    titles_set.remove(title)
    print 'other titles:', titles_set, '<br>'

    extra_isbn = set()
    for this_isbn in isbn_set:
        for isbn, note in find_others(this_isbn, rc['amazon_other_editions']):
            if note.lower().find('audio') != -1:
                continue
            if isbn not in isbn_set:
                extra_isbn.add(isbn)

    print 'more ISBN found:', extra_isbn, '<br>'

urls = (
    '/', 'index'
)

def textbox(name, input):
    if name in input:
        return '<input type="text" name="%s" value="%s" width="60">' % (name, web.htmlquote(input[name]))
    else:
        return '<input type="text" name="%s" width="60">' % (name)

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
