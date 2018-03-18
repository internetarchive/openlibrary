import web
from PyZ3950 import zoom
from lxml import etree
import sys, re
from urllib import urlopen
from openlibrary.catalog.marc.html import html_record
from openlibrary.catalog.marc import xml_to_html

tree = etree.parse('/petabox/www/petabox/includes/ztargets.xml')
root = tree.getroot()

targets = {}
for t in root:
    cur = {}
    if not isinstance(t.tag, str):
        continue
    for element in t:
        cur[element.tag] = element.text
    targets[cur['title']] = cur

re_identifier = re.compile('^([^:/]+)(?::(\d+))?(?:/(.+))?$')

def get_marc(target_name, cclquery, result_offset):
    target = targets[target_name]
    m = re_identifier.match(target['identifier'])
    (host, port, db) = m.groups()
    port = int(port) if port else 210
    conn = zoom.Connection (host, port)
    if db:
        conn.databaseName = db
    conn.preferredRecordSyntax = 'USMARC'
    query = zoom.Query ('PQF', cclquery)
    res = conn.search (query)
    offset = 0
    for r in res:
        return r.data
        offset += 1
        if offset == result_offset:
            return r.data

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
        marc_xml = 'http://www.archive.org/download/' + ia + '/' + ia + '_marc.xml'
        marc_bin = 'http://www.archive.org/download/' + ia + '/' + ia + '_meta.mrc'

        try:
            from_marc_xml = xml_to_html.html_record(urlopen(marc_xml).read())
        except:
            from_marc_xml = None

        try:
            meta_mrc = urlopen(marc_bin).read()
            from_marc_bin = html_record(meta_mrc)
        except:
            from_marc_bin = None

        root = etree.parse(urlopen(marc_source)).getroot()
        cclquery = root.find('cclquery').text
        target_name = root.find('target').text
        result_offset = root.find('resultOffset').text

        marc = get_marc(target_name, cclquery, result_offset)
        rec = html_record(marc)

        ret += '<h2>From Z39.50</h2>'

        ret += 'leader: <code>' + rec.leader.replace(' ', '&nbsp;') + '</code><br>'
        ret += rec.html() + '<br>\n'

        if from_marc_xml:
            ret += '<h2>From MARC XML on archive.org</h2>'

            ret += 'leader: <code>' + from_marc_xml.leader.replace(' ', '&nbsp;') + '</code><br>'
            ret += from_marc_xml.html() + '<br>\n'

        if from_marc_xml:
            ret += '<h2>From MARC binary on archive.org</h2>'

            ret += 'record length: ' + repr(len(meta_mrc)) + ' bytes<br>'
            ret += 'leader: <code>' + from_marc_bin.leader.replace(' ', '&nbsp;') + '</code><br>'
            ret += from_marc_bin.html() + '<br>\n'

        ret += '</body></html>'

        return ret

if __name__ == "__main__":
    app.run()

