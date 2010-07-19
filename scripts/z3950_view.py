import web
from PyZ3950 import zoom
from lxml import etree
import sys, re
from openlibrary.catalog.marc.html import html_record

tree = etree.parse('/petabox/www/petabox/includes/ztargets.xml')
root = tree.getroot()

targets = {}
for t in root:
    cur = {}
    if not isinstance(t.tag, str):
        continue
    for element in t:
        cur[element.tag] = element.text
    targets[cur['handle']] = cur

re_identifier = re.compile('^([^:]+):(\d+)(?:/(.+))?$')

def get_marc(target_id, cclquery):
    target = targets[target_id]
    m = re_identifier.match(target['identifier'])
    (host, port, db) = m.groups()
    port = int(port)
    
    conn = zoom.Connection (host, port)
    if db:
        conn.databaseName = db
    conn.preferredRecordSyntax = 'USMARC'
    query = zoom.Query ('PQF', cclquery)
    res = conn.search (query)
    for r in res:
        first = r.data
        break
    return first

urls = (
    '/z39.50/(.+)', 'z3950_lookup',
    '/z39.50', 'search_page',
    '/', 'index',
)
app = web.application(urls, globals())

class index:
    def GET(self):
        return '''
<html>
<head>
<title>Open Library labs</title>
</head>
<body>
<ul>
<li><a href="z39.50">Z39.50 lookup</a>
</ul>
</body>
<html>'''

class search_page:
    def GET(self):
        i = web.input()
        if 'ia' in i:
            raise web.seeother('/z39.50/' + i.ia.strip())
        return '''
<html>
<head>
<title>Z39.50 search</title>
</head>
<body>
<form>Internet archive identifier: <input name="ia"><input value="go" type="submit"></form>
</body>
<html>'''



class z3950_lookup:
    def GET(self, ia):

        ret = '''
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<title>Marc lookup: %s</title>
</head>
<body>
<form action="/z39.50">Internet archive identifier: <input name="ia" value="%s"><input value="go" type="submit"></form>
<h1>%s</h1>
<ul>
<li><a href="http://www.archive.org/details/%s">Internet archive detail page</a>
<li><a href="http://openlibrary.org/show-records/ia:%s">View current IA MARC record</a>
</ul>
''' % (ia, ia, ia, ia, ia)
        marc_source = 'http://www.archive.org/download/' + ia + '/' + ia + '_metasource.xml'
        root = etree.parse(marc_source).getroot()
        cclquery = root.find('cclquery').text
        target_id = root.find('target').attrib['id']

        marc = get_marc(target_id, cclquery)
        rec = html_record(marc)

        ret += 'leader: ' + rec.leader + '<br>'
        ret += rec.html()
        ret += '</body></html>'

        return ret

if __name__ == "__main__":
    app.run()

