import web, dbhash, re
from catalog.infostore import get_site
from catalog.get_ia import get_data
from catalog.read_rc import read_rc
from catalog.marc.build_record import build_record
from catalog.marc.fast_parse import get_all_subfields, get_tag_lines, get_first_tag, get_subfields

trans = {'&':'amp','<':'lt','>':'gt'}
re_html_replace = re.compile('([&<>])')

def esc(s):
    if not isinstance(s, basestring):
        return s
    return re_html_replace.sub(lambda m: "&%s;" % trans[m.group(1)], s.encode('utf8')).replace('\n', '<br>')

data_cache = {}
def marc_data(loc):
    if loc not in data_cache:
        data_cache[loc] = get_data(loc)
    return data_cache[loc]

def marc_authors(data):
    line = get_first_tag(data, set(['100', '110', '111']))
    return ''.join("<b>$%s</b>%s" % (esc(k), esc(v)) for k, v in get_all_subfields(line)) if line else None

def marc_publisher(data):
    line = get_first_tag(data, set(['260']))
    return ''.join("<b>$%s</b>%s" % (esc(k), esc(v)) for k, v in get_all_subfields(line)) if line else None

def marc_title(data):
    line = get_first_tag(data, set(['245']))
    return ''.join("<b>$%s</b>%s" % (esc(k), esc(v)) for k, v in get_subfields(line, set(['a', 'b', 'c']))) if line else None

def marc_by_statement(data):
    line = get_first_tag(data, set(['245']))
    return ''.join("<b>$%s</b>%s" % (esc(k), esc(v)) for k, v in get_subfields(line, set(['c']))) if line else None



rc = read_rc()

urls = (
    '/', 'index'
)

site = get_site()

db_isbn = dbhash.open(rc['index_path'] + 'isbn_to_marc.dbm', 'r')

def marc_table(l):
    print '<table>'
    print '<tr><td colspan="2">', l, "</td></tr>"
    data = marc_data(l)
    print '<tr><td>MARC author</td><td>', marc_authors(data), '</td></tr>'
    print '<tr><td>MARC by statement</td><td>', marc_by_statement(data), '</td></tr>'
    print '</table>'


class index:
    def GET(self):
        web.header('Content-Type','text/html; charset=utf-8', unique=True)
        key = web.input().author
        thing = site.get(key)
        title = ' - '.join([thing.name, key, 'Split author'])
        print "<html>\n<head>\n<title>%s</title>" % title
        print '''
<style>
th { text-align: left }
td { padding: 5px; background: #eee; vertical-align: top }
</style>'''

        print '</head><body><a name="top">'
        print thing.name, '<p>'
        for k in site.things({'type': '/type/edition', 'authors': key}):
            t = site.get(k)
            print '<a href="http://openlibrary.org%s">%s</a></td>' % (k, t.title)
            if t.isbn_10:
                isbn = str(t.isbn_10[0])
                locs = db_isbn[isbn].split(' ') if isbn in db_isbn else []
                print '(ISBN: <a href="http://wiki-beta.us.archive.org:8081/?isbn=%s">%s</a> <a href="http://amazon.com/dp/%s">Amazon</a>)' % (isbn, isbn, isbn)
            else:
                isbn = None
                locs = []
            if locs:
                for l in locs:
                    marc_table(l)
            print '<p>'
        print '<body><html>'

if __name__ == "__main__":
    web.run(urls, globals(), web.reloader)

