from catalog.infostore import get_site
import web
from catalog.marc.db.web_marc_db import search_query, show_locs

site = get_site()

def get_authors_by_name(name):
    return site.things({'name': name, 'type': '/type/author'})

def get_books_by_author(key):
    return site.things({'authors': key, 'type': '/type/edition'})

def author_search(author_key):
    book_keys = get_books_by_author(author_key)
    for key in book_keys:
        t = site.get(key)
        print key, t.title, '<br>'
        print '&nbsp;&nbsp;', t.isbn_10, '<br>'
        locs = []
        for i in t.isbn_10 if t.isbn_10 else []:
            for l in search_query('isbn', i):
                if l not in locs:
                    locs.append(l)
        for i in t.lccn if t.lccn else []:
            for l in search_query('lccn', i):
                if l not in locs:
                    locs.append(l)
        show_locs(locs, None)

urls = (
    '/', 'index'
)

class index():
    def GET(self):
        web.header('Content-Type','text/html; charset=utf-8', unique=True)
        input = web.input()
        author_key = input.get('author', None)
        print "<html>\n<head>\n<title>Author fixer</title>"
        print '''
<style>
th { text-align: left }
td { padding: 5px; background: #eee }
</style>'''

        print '</head><body><a name="top">'
        print '<form name="main" method="get">'
        if author_key:
            print '<input type="text" name="author" value="%s">' % web.htmlquote(author_key)
        else:
            print '<input type="text" name="author">'
        print '<input type="submit" value="find">'
        print '</form>'
        if author_key:
            author_search(author_key)
        print "</body></html>"


if __name__ == "__main__":
    web.run(urls, globals(), web.reloader)
