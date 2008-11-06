import web, dbhash
from catalog.read_rc import read_rc
from catalog.get_ia import get_data
from catalog.marc.build_record import build_record
from pprint import pprint
import re
from catalog.marc.sources import sources

trans = {'&':'amp','<':'lt','>':'gt','\n':'<br>'}
re_html_replace = re.compile('([ &<>])')

def esc(s):
    return re_html_replace.sub(lambda m: "&%s;" % trans[m.group(1)], s.encode('utf8'))

rc = read_rc()
db = dbhash.open(rc['index_path'] + 'isbn_to_marc.dbm', 'r')

srcs = dict(sources())

def src_list(loc):
    return '; '.join(srcs[l[:l.find('/')]] for l in loc)

def search(isbn):
    if isbn not in db:
        print isbn, ' not found'
        return

    recs = [(loc, build_record(get_data(loc))) for loc in db[isbn].split(' ')]
    keys = set()
    print "records found from %d libraries<br>" % len(recs)
    print '<ul>'
    for loc, rec in recs:
        s = srcs[loc[:loc.find('/')]]
        print '<li><a href="http://openlibrary.org/show-marc/%s">%s</a>' % (loc, s)
        keys.update([k for k in rec.keys()])
        for f in 'uri', 'languages':
            if f in rec:
                del rec[f]
    print '</ul>'
    keys -= set(['languages', 'uri'])
    print '<table>'
    first_key = True
    for k in keys:
        v = [(rec.get(k, None), loc) for loc, rec in recs]
        if all(i is None or (isinstance(i, list) and len(i) == 1) for i, loc in v):
            v = [ (i[0], loc) if i else (None, loc) for i, loc in v]

        if any(isinstance(i, list) or isinstance(i, dict) for i, loc in v):
            continue
        print '<tr><th>%s</th><td>' % k
        count = {}
        lens = [len(i) for i, loc in v if i and isinstance(i, basestring)]
        sep = '<br>' if lens and max(lens) > 20 else ' '
        for i, loc in v:
            if isinstance(i, basestring):
                i = i.rstrip('. ;:')
            count.setdefault(i, []).append(loc)
        s = sorted(count.iteritems(), cmp=lambda x,y: cmp(len(y[1]), len(x[1]) ))
        print sep.join('<b>%d</b>: <span title="%s">%s</span>' % (len(loc), src_list(loc), value or '<em>empty</em>') for value, loc in s)
        if first_key:
            print '<td valign="top" rowspan="%d"><img src="http://covers.openlibrary.org/b/isbn/%s-L.jpg">' % (len(keys), isbn)
            first_key = False
        print '</td></tr>'
    print '</table>'

urls = (
    '/', 'index'
)

class index():
    def GET(self):
        web.header('Content-Type','text/html; charset=utf-8', unique=True)
        input = web.input()
        if 'isbn' in input:
            isbn = input.isbn
            title = 'MARC lookup: ' + isbn
        else:
            isbn = None
            title = 'MARC lookup'
        print "<html>\n<head>\n<title>%s</title>" % title
        print '''
<style>
th { text-align: left }
td { padding: 5px; background: #eee }
</style>'''

        print '</head><body><a name="top">'
        print '<form name="main" method="get">'
        if isbn:
            print '<input type="text" name="isbn" value="%s">' % web.htmlquote(isbn)
        else:
            print '<input type="text" name="isbn">'
        print '<input type="submit">'
        print '</form><br>'
        if isbn:
            search(isbn)
        print "<body><html>"

if __name__ == "__main__": web.run(urls, globals(), web.reloader)
