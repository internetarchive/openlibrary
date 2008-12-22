import web, dbhash
from catalog.read_rc import read_rc
from catalog.get_ia import get_data
from catalog.marc.build_record import build_record
from catalog.marc.fast_parse import get_all_subfields, get_tag_lines, get_first_tag, get_subfields
from pprint import pprint
import re, sys, os.path, random
from catalog.marc.sources import sources
from catalog.amazon.other_editions import find_others
from catalog.infostore import get_site

site = get_site()

rc = read_rc()

trans = {'&':'amp','<':'lt','>':'gt'}
re_html_replace = re.compile('([&<>])')

def marc_authors(data):
    line = get_first_tag(data, set(['100', '110', '111']))
    return ''.join("<b>$%s</b>%s" % (esc(k), esc(v)) for k, v in get_all_subfields(line)) if line else None

def marc_title(data):
    line = get_first_tag(data, set(['245']))
    return ''.join("<b>$%s</b>%s" % (esc(k), esc(v)) for k, v in get_subfields(line, set(['a', 'b']))) if line else None

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
        if isbn in db_isbn and len(db_isbn[isbn].split(' ')) > 1:
            break
    f.close()
    return isbn

def esc(s):
    if not isinstance(s, basestring):
        return s
    return re_html_replace.sub(lambda m: "&%s;" % trans[m.group(1)], s.encode('utf8')).replace('\n', '<br>')

db_isbn = dbhash.open(rc['index_path'] + 'isbn_to_marc.dbm', 'r')
db_lccn = dbhash.open(rc['index_path'] + 'lccn.dbm', 'r')

srcs = dict(sources())

def src_list(loc):
    return '; '.join(srcs[l[:l.find('/')]] for l in loc)

data_cache = {}
def marc_data(loc):
    if loc not in data_cache:
        data_cache[loc] = get_data(loc)
    return data_cache[loc]

def counts_html(v):
    count = {}
    lens = [len(i) for i, loc in v if i and isinstance(i, basestring)]
    sep = '<br>' if lens and max(lens) > 20 else ' '
    for i, loc in v:
        count.setdefault(i, []).append(loc)
    s = sorted(count.iteritems(), cmp=lambda x,y: cmp(len(y[1]), len(x[1]) ))
    return sep.join('<b>%d</b>: <span title="%s">%s</span>' % (len(loc), src_list(loc), value if value else '<em>empty</em>') for value, loc in s)

def list_works(this_isbn):
    works = find_others(this_isbn, rc['amazon_other_editions'])
    print '<a name="work">'
    print '<h2>Other editions of the same work</h2>'
    if not works:
        print 'no work found'
        return
    print '<table>'
    print '<tr><th>ISBN</th><th>Amazon edition</th><th></th><th>MARC titles</th></tr>'
    for isbn, note in works:
        if note.lower().find('audio') != -1:
            continue
        locs = db_isbn[isbn].split(' ') if isbn in db_isbn else []
#        titles = [read_full_title(get_first_tag(marc_data(i), set(['245'])), accept_sound = True) for i in locs]
        titles = [(marc_title(marc_data(i)), i) for i in locs]
        num = len(locs)
        #print '<tr><td><a href="/?isbn=%s">%s</a></td><td>%s</td><td>%d</td><td>%s</td></tr>' % (isbn, isbn, note, len(locs), list_to_html(titles))
        print '<tr><td><a href="/?isbn=%s">%s</a></td><td>%s</td><td>%d</td><td>' % (isbn, isbn, note, len(locs))
        print counts_html(titles)
        print '</td></tr>'
    print '</table>'

def most_freq_isbn(input):
    counts = {}
    for a in input:
        for b in a[0]:
            counts[b] = counts.get(b, 0) + 1
    return max(counts, key=counts.get)

def show_locs(locs, isbn):
    recs = [(loc, build_record(marc_data(loc))) for loc in locs]
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
    for f in ['isbn_10', 'title', 'subtitle', 'by_statement', 'authors', 'contributions']:
        if f in keys:
            first += [f]
            keys -= set([f])
    for k in first + list(keys):
        v = [(rec.get(k, None), loc) for loc, rec in recs]
        if k == 'isbn_10':
            if not isbn:
                isbn = most_freq_isbn(v)
        if k == 'languages':
            v = [([ i['key'][3:] for i in l ] if l else None, loc) for l, loc in v]
        if all(i is None or (isinstance(i, list) and len(i) == 1) for i, loc in v):
            v = [ (i[0] if i else None, loc) for i, loc in v]

        print '<tr><th valign="top">%s</th><td>' % k
        if any(isinstance(i, list) or isinstance(i, dict) for i, loc in v):
            if k == 'authors': # easiest to switch to raw MARC display
                v = [(marc_authors(marc_data(loc)), loc) for i, loc in v ]
            elif k == 'isbn_10':
                v = [ (list_to_html(sorted(i)), loc) if i else (None, loc) for i, loc in v]
            else:
                v = [ (list_to_html(i), loc) if i else (None, loc) for i, loc in v]
        else:
            v = [ (esc(i), loc) for i, loc in v]
#        print `[i[0] for i in v]`, '<br>'
        print counts_html(v)
        if isbn and first_key:
            print '<td valign="top" rowspan="%d"><img src="http://covers.openlibrary.org/b/isbn/%s-L.jpg">' % (len(first) + len(keys), isbn)
            first_key = False
        print '</td></tr>'
    print '</table>'

def search_lccn(lccn):
    if lccn not in db_lccn:
        print lccn, ' not found'
        return
    show_locs(db_lccn[lccn].split(' '), None)

def search_isbn(isbn):
    things = site.things({'type': '/type/edition', 'isbn_10': isbn})
    if things:
        print ', '.join('<a href="http://openlibrary.org%s">%s</a>' % (k, k) for k in things), '<br>'
        
    if isbn not in db_isbn:
        print isbn, ' not found'
        return

    print '<a href="#work">skip to other editions of the same work</a><br>'
    show_locs(db_isbn[isbn].split(' '), isbn)
    list_works(isbn)
#    rec_data = dict((loc, get_data(loc)) for loc in locs)

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
        print "<html>\n<head>\n<title>%s</title>" % title
        print '''
<style>
th { text-align: left }
td { padding: 5px; background: #eee }
</style>'''

        print '</head><body><a name="top">'
        print '<form name="main" method="get"><table><tr><td align="right">ISBN</td><td>'
        if isbn:
            print '<input type="text" name="isbn" value="%s">' % web.htmlquote(isbn)
        else:
            print '<input type="text" name="isbn">'
        print ' or <a href="/random">random</a><br>'
        print '</td></tr><tr><td align="right">LCCN</td><td>'
        if lccn:
            print '<input type="text" name="lccn" value="%s">' % web.htmlquote(lccn)
        else:
            print '<input type="text" name="lccn">'
        print '</td></tr>',
        print '<tr><td></td><td><input type="submit" value="find"></td></tr>'
        print '</table>'
        print '</form>'
        if isbn:
            search_isbn(isbn)
        elif lccn:
            search_lccn(lccn)
        print "<body><html>"

if __name__ == "__main__": web.run(urls, globals(), web.reloader)
