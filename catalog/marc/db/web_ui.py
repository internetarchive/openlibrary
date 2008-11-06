import web, dbhash
from catalog.read_rc import read_rc

rc = read_rc()
db = dbhash.open(rc['index_path'] + 'isbn_to_marc.dbm', 'r')

def search(isbn):
    if isbn in db:
        print db[isbn]
    else:
        print isbn, ' not found'
# 0689838425

urls = (
    '/', 'index'
)

class index():
    def GET(self):
        web.header('Content-Type','text/html; charset=utf-8', unique=True)
        input = web.input()
        if 'isbn' in input:
            title = 'MARC lookup: ' + input.isbn
        else:
            title = 'MARC lookup'
        print "<html>\n<head>\n<title>%s</title></head>" % title
        print '<body><a name="top">'
        print '<form name="main" method="get">'
        if 'isbn' in input:
            print '<input type="text" name="isbn" value="%s">' % web.htmlquote(input.isbn)
        else:
            print '<input type="text" name="isbn">'
        print '<input type="submit">'
        print '</form>'
        search(isbn)
        print "<body><html>"

web.webapi.internalerror = web.debugerror

if __name__ == "__main__": web.run(urls, globals(), web.reloader)
