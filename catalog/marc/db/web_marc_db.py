# lookup MARC records and show details on the web
from catalog.read_rc import read_rc
from catalog.get_ia import get_data
from catalog.marc.build_record import build_record
from catalog.marc.fast_parse import get_all_subfields, get_tag_lines, get_first_tag, get_subfields
from pprint import pprint
import re, sys, os.path, web
#from catalog.amazon.other_editions import find_others
from catalog.utils import strip_count

db = web.database(dbn='postgres', db='marc_lookup')
db.printing = False

trans = {'&':'amp','<':'lt','>':'gt'}
re_html_replace = re.compile('([&<>])')

def marc_authors(data):
    line = get_first_tag(data, set(['100', '110', '111']))
    return ''.join("<b>$%s</b>%s" % (esc(k), esc(v)) for k, v in get_all_subfields(line)) if line else None

def marc_publisher(data):
    line = get_first_tag(data, set(['260']))
    return ''.join("<b>$%s</b>%s" % (esc(k), esc(v)) for k, v in get_all_subfield)

def marc_title(data):
    line = get_first_tag(data, set(['245']))
    return ''.join("<b>$%s</b>%s" % (esc(k), esc(v)) for k, v in get_subfields(line, set(['a', 'b']))) if line else None

def find_isbn_file():
    for p in sys.path:
        f = p + "/catalog/isbn"
        if os.path.exists(f):
            return f

#isbn_file = find_isbn_file()
#isbn_count = os.path.getsize(isbn_file) / 11

def list_to_html(l):
    def blue(s):
        return ' <span style="color:blue; font-weight:bold">%s</span> ' % s
    return blue('[') + blue('|').join(l) + blue(']')

def esc(s):
    if not isinstance(s, basestring):
        return s
    return re_html_replace.sub(lambda m: "&%s;" % trans[m.group(1)], s.encode('utf8')).replace('\n', '<br>')

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
    s = strip_count(s)
    return sep.join('<b>%d</b>: <span title="%s">%s</span>' % (len(loc), `loc`, value if value else '<em>empty</em>') for value, loc in s)

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
        if a:
            for b in a[0]:
                counts[b] = counts.get(b, 0) + 1
    return max(counts, key=counts.get)

def show_locs(locs, isbn):
    recs = [(loc, build_record(marc_data(loc))) for loc in locs]
    keys = set()
    ret = "records found from %d libraries<br>" % len(recs)
    ret += '<ul>'
    for loc, rec in recs:
        s = loc[:loc.find('/')]
        ret += '<li><a href="http://openlibrary.org/show-marc/%s">%s</a>' % (loc, s)
        keys.update([k for k in rec.keys()])
        for f in 'uri':
            if f in rec:
                del rec[f]
    ret += '</ul>'
    keys -= set(['uri'])
    ret += '<table>'
    first_key = True
    first = []
    for f in ['isbn_10', 'title', 'subtitle', 'by_statement', 'authors', 'contributions']:
        if f in keys:
            first += [f]
            keys -= set([f])
    for k in first + list(keys):
        v = [(rec.get(k, None), loc) for loc, rec in recs]
#        if k == 'isbn_10' and not isbn and v:
#            isbn = most_freq_isbn(v)
        if k == 'languages':
            v = [([ i['key'][3:] for i in l ] if l else None, loc) for l, loc in v]
        if all(i is None or (isinstance(i, list) and len(i) == 1) for i, loc in v):
            v = [ (i[0] if i else None, loc) for i, loc in v]

        ret += '<tr><th valign="top">%s</th><td>' % k
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
        ret += counts_html(v)
        if isbn and first_key:
            ret += '<td valign="top" rowspan="%d"><img src="http://covers.openlibrary.org/b/isbn/%s-L.jpg">' % (len(first) + len(keys), isbn)
            first_key = False
        ret += '</td></tr>'
    ret += '</table>'
    return ret

def search_query(field, value):
    sql = 'select part, pos, len ' \
        + 'from files, recs, ' + field \
        + ' where ' + field + '.rec=recs.id and recs.marc_file=files.id and value=$v'
    iter = db.query(sql, {'v': value})
    return [':'.join([i.part.strip(), str(i.pos), str(i.len)]) for i in iter]
