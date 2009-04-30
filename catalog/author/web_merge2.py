import web, re
from urllib2 import urlopen
import simplejson as json
from pprint import pformat

from catalog.utils.query import query_iter

urls = (
    '/', 'index'
)
app = web.application(urls, globals())

re_year = re.compile('^(\d+)[,.*]+$')

def result_table(data, birth, death, order):
    html = ' %d results' % len(data)
    l = []
    def clean(i, default, field):
        if field not in i:
            return default
        if i[field] is None:
            return ''
        m = re_year.match(i[field])
        return m.group(1) if m else i[field]
 
    data = [
        {
            'key': i['key'],
            'name': i['name'],
            'birth': clean(i, birth, 'birth_date'),
            'death': clean(i, death, 'death_date'),
        } for i in data]
               
    base_url = web.htmlquote("?birth=%s&death=%s&order=" % (web.urlquote(birth), web.urlquote(death)))
    html += '<tr>'
    html += '<th><a href="' + base_url + 'name">Name</a></th>'
    if birth:
        html += '<th>birth</th>'
    else:
        html += '<th><a href="' + base_url + 'birth">birth</a></th>'
    if death:
        html += '<th>death</th>'
    else:
        html += '<th><a href="' + base_url + 'death">death</a></th>'
    html += '</tr>'
    if order:
        data = sorted(data, key=lambda i:i[order])
    for i in data:
        html += '<tr><td><a href="http://openlibrary.org%s">%s</td><td>%s</td><td>%s</td><tr>' % (i['key'], web.htmlquote(i['name']), i['birth'], i['death'])
    return '<table>' + html + '</table>'

def get_all(url):
    all = []
    offset = 0
    limit = 500
    while True:
        ret = json.load(urlopen(url + "&limit=%d&offset=%d" % (limit, offset)))
        if not ret:
            return all
        all += ret
        if len(all) >= 1000:
            return all
        offset += limit

class index:        
    def GET(self):
        input = web.input()
        birth = input.get('birth', '').strip()
        death = input.get('death', '').strip()
        order = input.get('order', '').strip()
        if order not in ('', 'name', 'birth', 'death'):
            order = ''
        html = '''
<html>
<head>
<meta http-equiv="content-type" content="text/html; charset=UTF-8">
<title>Merge author</title>
<style>
body { font-family: arial,helvetica,san-serif; }
th { text-align: left; }
</style>
</head>
<body>
'''
        html += '<form method="get">\n'
        html += 'Birth: <input type="text" size="7" name="birth" value="%s">\n' % web.htmlquote(birth)
        html += 'Death: <input type="text" size="7" name="death" value="%s">\n' % web.htmlquote(death)
        html += '<input type="submit" value="Search">\n</form>'

        if birth or death:
            url = 'http://openlibrary.org/query.json?type=/type/author&birth_date=%s&death_date=%s&name=' % (web.urlquote(birth), web.urlquote(death))
            data = get_all(url)
            html += result_table(data, birth, death, order)
        return html + '</body>\n</html>'

if __name__ == "__main__":
    app.run()
