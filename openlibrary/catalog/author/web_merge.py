import web
from catalog.db_read import withKey
from pprint import pformat

urls = (
    '/', 'index'
)

base = 'http://openlibrary.org'

class index:
    def GET(self):
        web.header('Content-Type','text/html; charset=utf-8', unique=True)
        input = web.input()
        print "<html>\n<head><title>Author merge</title></head><body>"
        print "<h1>Author merge</h1>"
        print '<form name="main" method="get">'
        print '<table>'
        print '<tr><td>Authors</td>'
        author = {}
        for field in ('a', 'b'):
            print '<td>'
            if field in input:
                key = input[field]
                if key.startswith(base):
                    key = key[len(base):]
                author[field] = withKey(key)
                print '<input type="text" name="%s" value="%s">' % (field, key)
            else:
                print '<input type="text" name="%s">' % field
            print '</td>'
        print '<td><input type="submit" value="Load"></td>'
        print '</tr>'
        if 'a' in author and 'b' in author:
            a = author['a']
            b = author['b']
            keys = [withKey(prop['key'])['name'] for prop in withKey('/type/author')['properties']]
            for k in keys:
                if k in a or k in b:
                    print '<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % \
                            (k, a.get(k, ''), b.get(k, ''))
        print '</table>'
        print "</body></html>"

web.webapi.internalerror = web.debugerror

if __name__ == "__main__": web.run(urls, globals(), web.reloader)
