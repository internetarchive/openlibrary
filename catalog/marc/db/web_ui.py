import web, dbhash
from catalog.read_rc import read_rc
from catalog.get_ia import get_data
from catalog.marc.build_record import build_record
from catalog.marc.fast_parse import get_all_subfields, get_tag_lines, get_first_tag
from pprint import pprint
import re, sys, os.path, random
from catalog.marc.sources import sources
from catalog.amazon.other_editions import find_others

rc = read_rc()

trans = {'&':'amp','<':'lt','>':'gt'}
re_html_replace = re.compile('([&<>])')

def marc_authors(data):
    line = get_first_tag(data, set(['100', '110', '111']))
    return ''.join("<b>$%s</b>%s" % (esc(k), esc(v)) for k, v in get_all_subfields(line)) if line else None

def find_isbn_file():
    for p in sys.path:
        f = p + "/catalog/isbn"
        if os.path.exists(f):
            return f

isbn_file = find_isbn_file()
isbn_count = os.path.getsize(isbn_file) / 11

def list_to_html(l):
    def blue(s):
        return ' <span style="color:blue; font-weight:bold">%s</span> ' % s
    return blue('[') + blue('|').join(l) + blue(']')

def random_isbn():
    f = open(isbn_file)
    while 1:
        f.seek(random.randrange(isbn_count) * 11)
        isbn = f.read(10)
        if isbn in db and len(db[isbn].split(' ')) > 1:
            break
    f.close()
    return isbn

def esc(s):
    if not isinstance(s, basestring):
        return s
    return re_html_replace.sub(lambda m: "&%s;" % trans[m.group(1)], s.encode('utf8')).replace('\n', '<br>')

db = dbhash.open(rc['index_path'] + 'isbn_to_marc.dbm', 'r')

srcs = dict(sources())

def src_list(loc):
    return '; '.join(srcs[l[:l.find('/')]] for l in loc)

def list_works(this_isbn):
    works = find_others(this_isbn, rc['amazon_other_editions'])
    print '<h2>Other editions of the same work</h2>'
    print '<table>'
    for isbn, note in works:
        num = len(db[isbn].split(' ')) if isbn in db else 0
        print '<tr><td><a href="/?isbn=%s">%s</a></td><td>%s</td><td>%d</td></tr>' % (isbn, isbn, note, num)
    print '</table>'

def search(isbn):
    if isbn not in db:
        print isbn, ' not found'
        return

    locs = db[isbn].split(' ')
    rec_data = dict((loc, get_data(loc)) for loc in locs)
    recs = [(loc, build_record(rec_data[loc])) for loc in locs]
    keys = set()
    print "records found from %d libraries<br>" % len(recs)
    print '<ul>'
    for loc, rec in recs:
        s = srcs[loc[:loc.find('/')]]
        print '<li><a href="http://openlibrary.org/show-marc/%s">%s</a>' % (loc, s)
        keys.update([k for k in rec.keys()])
        for f in 'uri':
            if f in rec:
                del rec[f]
    print '</ul>'
    keys -= set(['uri'])
    print '<table>'
    first_key = True
    first = []
    for f in ['title', 'subtitle', 'by_statement', 'authors', 'contributions']:
        if f in keys:
            first += [f]
            keys -= set([f])
    for k in first + list(keys):
        v = [(rec.get(k, None), loc) for loc, rec in recs]
        if k == 'languages':
            v = [([ i['key'][3:] for i in l ] if l else None, loc) for l, loc in v]
        if all(i is None or (isinstance(i, list) and len(i) == 1) for i, loc in v):
            v = [ (i[0] if i else None, loc) for i, loc in v]

        print '<tr><th>%s</th><td>' % k
        if any(isinstance(i, list) or isinstance(i, dict) for i, loc in v):
            if k == 'authors': # easiest to switch to raw MARC display
                v = [(marc_authors(rec_data[loc]), loc) for i, loc in v ]
            else:
                v = [ (list_to_html(i), loc) if i else (None, loc) for i, loc in v]
        else:
            v = [ (esc(i), loc) for i, loc in v]
        count = {}
        lens = [len(i) for i, loc in v if i and isinstance(i, basestring)]
        sep = '<br>' if lens and max(lens) > 20 else ' '
        for i, loc in v:
            count.setdefault(i, []).append(loc)
        s = sorted(count.iteritems(), cmp=lambda x,y: cmp(len(y[1]), len(x[1]) ))
        print sep.join('<b>%d</b>: <span title="%s">%s</span>' % (len(loc), src_list(loc), value if value else '<em>empty</em>') for value, loc in s)
        if first_key:
            print '<td valign="top" rowspan="%d"><img src="http://covers.openlibrary.org/b/isbn/%s-L.jpg">' % (len(first) + len(keys), isbn)
            first_key = False
        print '</td></tr>'
    print '</table>'
    list_works(isbn)

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
        if 'isbn' in input:
            isbn = input.isbn
            if isbn == 'random':
                isbn = random_isbn()
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
        print '<form name="main" method="get"> ISBN:'
        if isbn:
            print '<input type="text" name="isbn" value="%s">' % web.htmlquote(isbn)
        else:
            print '<input type="text" name="isbn">'
        print '<input type="submit" value="find">'
        print '</form> or <a href="/random">random</a><br>'
        if isbn:
            search(isbn)
        print "<body><html>"

if __name__ == "__main__": web.run(urls, globals(), web.reloader)
