import web, re, httplib, sys, codecs
from lxml.etree import tostring, Element
from time import time

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

db = web.database(dbn='mysql', db='openlibrary')
db.printing = False

re_year = re.compile(r'(\d{4})$')
re_author_key = re.compile('^/a/OL(\d+)A$')
re_work_key = re.compile('^/works/OL(\d+)W$')

solr_host = 'localhost:8983'
update_url = 'http://' + solr_host + '/solr/authors/update'

connect = False

def solr_post(h1, body):
    if not connect:
        return 'not connected'
    h1.request('POST', update_url, body, { 'Content-type': 'text/xml;charset=utf-8'})
    response = h1.getresponse()
    response.read()
    return response.reason

h1 = None
if connect:
    h1 = httplib.HTTPConnection(solr_host)
    h1.connect()
    print solr_post(h1, '<delete><query>*:*</query></delete>')
    print solr_post(h1, '<commit/>')

re_bad_char = re.compile('[\x01\x19-\x1e]')
def strip_bad_char(s):
    if not isinstance(s, basestring):
        return s
    return re_bad_char.sub('', s)

def add_field(doc, name, value):
    field = Element("field", name=name)
    field.text = unicode(strip_bad_char(value))
    doc.append(field)

def add_field_list(doc, name, field_list):
    for value in field_list:
        add_field(doc, name, value)

def u8(s):
    if s is not None:
        return s.decode('utf-8')

def work_title(wkey):
    return u8(db.query('select title from works where wkey=$wkey', vars=locals())[0].title)

total = db.query('select count(*) as total from authors')[0].total
num = 0
add = Element("add")
for row in db.query('select * from authors'):
    num += 1

    doc = Element("doc")
    add_field(doc, 'key', 'OL%dA' % row.akey)
    name = u8(row.name)
    if name is None:
        continue
    add_field(doc, 'name', name)
    add_field(doc, 'name_str', name.lower())
    if row.alt_names is not None:
        add_field_list(doc, 'alternate_names', u8(row.alt_names).split('\t'))
    for f in 'birth_date', 'death_date', 'date':
        if row[f] is not None:
            add_field(doc, f, u8(row[f]))

    if row.top_work:
        wt = work_title(row.top_work)
        if wt:
            add_field(doc, 'top_work', wt)

    f = 'top_subjects'
    if row[f] is not None:
        add_field_list(doc, f, u8(row[f]).split('\t'))

    add.append(doc)

    if len(add) == 100:
        add_xml = tostring(add, pretty_print=True).encode('utf-8')
        del add
        print "%d/%d %.4f%%" % (num,total,(float(num)*100.0/total)), solr_post(h1, add_xml)
        add = Element("add")

if len(add):
    add_xml = tostring(add, pretty_print=True).encode('utf-8')
    del add
    print solr_post(h1, add_xml)
print 'end'
print solr_post(h1, '<commit/>')
print solr_post(h1, '<optimize/>')
