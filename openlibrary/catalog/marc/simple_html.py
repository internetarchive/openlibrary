#!/usr/bin/python2.5
from catalog.marc.fast_parse import *
from html import as_html
from build_record import build_record
import sys, re

trans = {'&':'&amp;','<':'&lt;','>':'&gt;','\n':'<br>'}
re_html_replace = re.compile('([&<>\n])')

def esc(s):
    return re_html_replace.sub(lambda m: trans[m.group(1)], s.encode('utf8'))

fields = [
    ('title', 'Title'),
    ('subtitle', 'Subtitle'),
    ('by_statement', 'By statement'),
    ('authors', 'Authors'),
    ('contributions', 'Contributions'),
    ('edition_name', 'Edition'),
    ('publish_date', 'Publish date'),
    ('publishers', 'Publishers'),
    ('publish_places', 'Publish places'),
    ('publish_country', 'Publish country'),
    ('work_titles', 'Work titles'),
    ('other_titles', 'Other titles'),
    ('pagination', 'Pagination'),
    ('number_of_pages', 'Number of pages'),
    ('lc_classifications', 'LC classifications'),
    ('dewey_decimal_class', 'Dewey decimal class'),
    ('oclc_number', 'OCLC number'),
    ('lccn', 'LCCN'),
    ('series', 'Series'),
    ('genres', 'Genres'),
    ('languages', 'Languages'),
    ('subjects', 'Subjects'),
    ('description', 'Description'),
    ('notes', 'Notes'),
    ('uri', 'URL'),
    ('table_of_contents', 'Table of contents'),
]

re_end_dot = re.compile('[^ ][^ ]\.$', re.UNICODE)
re_marc_name = re.compile('^(.*), (.*)$')
re_year = re.compile(r'\b(\d{4})\b')

def flip_name(name):
    # strip end dots like this: "Smith, John." but not like this: "Smith, J."
    m = re_end_dot.search(name)
    if m:
        name = name[:-1]

    if name.find(', ') == -1:
        return name
    m = re_marc_name.match(name)
    return m.group(2) + ' ' + m.group(1)

def html_author(a):
    extra = ''
    et = a['entity_type']
    if et == 'person':
        a['name'] = flip_name(a['name'])
        if 'date' in a:
            extra = ", " + a['date']
        elif 'birth_date' in a or 'death_date' in a:
            extra = ", " + a.get('birth_date', '') + ' - ' + a.get('death_date', '')
    elif et == 'org':
        et = 'organization'
    return '<b>' + et + ':</b> ' + esc(a['name'] + extra)

def output_record_as_html(rec):
    rows = []
    rec.setdefault('number_of_pages', None)
    for k, label in fields:
        if k not in rec:
#            rows.append('<tr><th>%s</th><td>%s</td></tr>\n' % (label, '<em>empty</em>'))
            continue
        if k == 'authors':
            v = '<br>\n'.join(html_author(a) for a in rec[k])
        elif k == 'languages':
            v = ','.join(esc(i['key'][3:]) for i in rec[k])
        elif isinstance(rec[k], list):
            v = '<br>\n'.join(esc(i) for i in rec[k])
        elif rec[k] is None:
            v = '<em>empty</em>'
        else:
            v = esc(unicode(rec[k]))
        rows.append('<tr><th>%s</th><td>%s</td></tr>\n' % (label, v))

    return '<table>' + ''.join(rows) + '</table>'

style = """<style>
td,th { padding: 3px; }
tr { background: #eee; }
th { text-align: left; vertical-align: top; }
</style>"""

dir = sys.argv[2]

index = open(dir + "/index.html", "w")
print >> index, "<html>\n<head><title>MARC records</title>" + style + "</head>\n<body>\n<ul>"

rec_no = 0
for data, length in read_file(open(sys.argv[1])):
    rec_no += 1
    rec = build_record(data)
    title = rec['title'] 
    filename = dir + "/" + str(rec_no) + ".html"
    f = open(filename, 'w')
    print >> f, "<html>\n<head><title>" + title + "</title>" + style + "</head>\n<body>"
    print >> f, '<a href="index.html">Back to index</a><br>'
    print >> f, output_record_as_html(rec)
    print >> f, "<h2>MARC record</h2>"
    print >> f, as_html(data)
    print >> f, '<br>\n<a href="index.html">Back to index</a>'
    print >> f, "</body></html>"
    print >> index, '<li><a href="%d.html">%s</a>' % (rec_no, title)

print >> index, "</ul>\n</body></html>"
