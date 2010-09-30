#!/usr/bin/python2.5
import random
import web
from web_marc_db import search_query, show_locs

# too slow
#def random_isbn():
#    sql = "select value from isbn order by random() limit 1"
#    return list(web.query(sql))[0].value

isbn_file = '../../isbn'
isbn_count = 9093242

def random_isbn():
    f = open(isbn_file)
    while 1:
        f.seek(random.randrange(isbn_count) * 11)
        isbn = f.read(10)
        break
        found = list(web.select('isbn', where='value=$v', vars={'v':isbn}))
        if found > 1:
            break
    f.close()
    return isbn

def search(field, value):
    locs = search_query(field, value)
    print locs
    if locs:
        return show_locs(locs, value if field == 'isbn' else None)
    else:
        return value + ' not found'

urls = (
    '/random', 'rand',
    '/', 'index'
)

class rand():
    def GET(self):
        isbn = random_isbn()
        web.redirect('/?isbn=' + isbn)

class index():
    def GET(self):
        web.header('Content-Type','text/html; charset=utf-8', unique=True)
        input = web.input()
        lccn = None
        oclc = None
        isbn = None
        title = 'MARC lookup'
        if 'isbn' in input and input.isbn:
            isbn = input.isbn
            if isbn == 'random':
                isbn = random_isbn()
            title = 'MARC lookup: isbn=' + isbn
        if 'lccn' in input and input.lccn:
            lccn = input.lccn
            title = 'MARC lookup: lccn=' + lccn
        if 'oclc' in input and input.oclc:
            oclc = input.oclc
            title = 'MARC lookup: oclc=' + oclc
        ret = "<html>\n<head>\n<title>%s</title>" % title
        ret += '''
<style>
th { text-align: left }
td { padding: 5px; background: #eee }
</style>'''

        ret += '</head><body><a name="top">'
        ret += '<form name="main" method="get"><table><tr><td align="right">ISBN</td><td>'
        if isbn:
            ret += '<input type="text" name="isbn" value="%s">' % web.htmlquote(isbn)
        else:
            ret += '<input type="text" name="isbn">'
        ret += ' or <a href="/random">random</a><br>'
        ret += '</td></tr><tr><td align="right">LCCN</td><td>'
        if lccn:
            ret += '<input type="text" name="lccn" value="%s">' % web.htmlquote(lccn)
        else:
            ret += '<input type="text" name="lccn">'
        ret += '</td></tr><tr><td align="right">OCLC</td><td>'
        if oclc:
            ret += '<input type="text" name="oclc" value="%s">' % web.htmlquote(oclc)
        else:
            ret += '<input type="text" name="oclc">'
        ret += '</td></tr>'
        ret += '<tr><td></td><td><input type="submit" value="find"></td></tr>'
        ret += '</table>'
        ret += '</form>'
        if isbn:
            ret += search('isbn', isbn)
        elif lccn:
            search('lccn', lccn)
        elif oclc:
            search('oclc', oclc)
        ret += "</body></html>"
        return ret

app = web.application(urls, globals())

if __name__ == "__main__":
    app.run()
