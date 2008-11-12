import web
#from catalog.infostore import get_site
from catalog.db_read import get_things, withKey
from pprint import pprint

#site = get_site()

def search(title, author):
    q = { 'type': '/type/author', 'name': author }
    authors = get_things(q)
    print '<pre>'
    for a in authors:
        pprint(withKey(a))
        q = { 'type': '/type/edition', 'authors': a }
        print get_things(q)
    print '</pre>'

urls = (
    '/', 'index'
)

def textbox(name, input):
    if name in input:
        return '<input type="text" name="%s" value="%s">' % (name, web.htmlquote(input[name]))
    else:
        return '<input type="text" name="%s">' % (name)

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
        title = 'Work finder'
        print "<html>\n<head>\n<title>%s</title>" % title
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
