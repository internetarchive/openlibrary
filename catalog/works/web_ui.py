import web, re
from catalog.infostore import get_site
#from catalog.db_read import get_things, withKey
from pprint import pprint

re_translation_of = re.compile('^Translation of\b[: ]*(.*)$', re.I, re.M)

site = get_site()

def search(title, author):
    q = { 'type': '/type/edition', 'title': title }
#    print site.things(q)
    q = { 'type': '/type/author', 'name': author }
    authors = site.things(q)
    pool = []
    for a in authors:
        q = { 'type': '/type/edition', 'authors': a, 'title': title }
        pool += site.things(q)
    if not pool:
        return
    for key in pool:
        e = site.withKey(key)
        print key, e.title, e.work_titles, '<br>'
        if e.notes:
            print e.notes.replace('\n', '<br>'), '<p>'
        print '<hr>'

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
