from infogami.utils import delegate, stats
from infogami.utils.view import render_template
from lxml import etree

import re, web, urllib, simplejson, httplib

re_query_parser_error = re.compile(r'<pre>org.apache.lucene.queryParser.ParseException: (.*)</pre>', re.S)
re_solr_range = re.compile(r'\[.+\bTO\b.+\]', re.I)
re_bracket = re.compile(r'[\[\]]')
re_to_esc = re.compile(r'[\[\]:]')
def escape_bracket(q):
    if re_solr_range.search(q):
        return q
    return re_bracket.sub(lambda m:'\\'+m.group(), q)

trans = { '\n': '<br>', '{{{': '<b>', '}}}': '</b>', }
re_trans = re.compile(r'(\n|\{\{\{|\}\}\})')
def quote_snippet(snippet):
    return re_trans.sub(lambda m: trans[m.group(1)], web.htmlquote(snippet))

solr_select_url = 'http://ia331509:8984/solr/inside/select'

def editions_from_ia(ia):
    q = {'type': '/type/edition', 'ocaid': ia}
    editions = web.ctx.site.things(q)
    if not editions:
        q = {'type': '/type/edition', 'source_records': 'ia:' + ia}
        editions = web.ctx.site.things(q)
    return editions

def read_from_archive(ia):
    meta_xml = 'http://www.archive.org/download/' + ia + '/' + ia + '_meta.xml'
    tree = etree.parse(meta_xml)
    root = tree.getroot()
    item = {}

    fields = ['title', 'creator', 'publisher', 'date', 'language']

    for k in 'title', 'date', 'publisher':
        v = root.find(k)
        if v is not None:
            item[k] = v.text

    for k in 'creator', 'language':
        v = root.findall(k)
        if len(v):
            item[k] = [i.text for i in v]

    return item

class search_inside(delegate.page):
    path = '/search/inside'

    def GET(self):
        def get_results(q, offset=0, limit=100, snippets=3, fragsize=200):
            q = escape_bracket(q)
            solr_select = solr_select_url + "?fl=ia,body_length,page_count&hl=true&hl.fl=body&hl.snippets=%d&hl.mergeContiguous=true&hl.usePhraseHighlighter=true&hl.simple.pre={{{&hl.simple.post=}}}&hl.fragsize=%d&q.op=AND&q=%s&start=%d&rows=%d&qf=body&qt=standard&hl.maxAnalyzedChars=1000000&wt=json" % (snippets, fragsize, web.urlquote(q), offset, limit)
            print solr_select
            stats.begin("solr", url=solr_select)
            json_data = urllib.urlopen(solr_select).read()
            stats.end()
            try:
                return simplejson.loads(json_data)
            except:
                m = re_query_parser_error.search(json_data)
                return { 'error': web.htmlunquote(m.group(1)) }

        return render_template('search/inside.tmpl', get_results, quote_snippet, editions_from_ia, read_from_archive)

def ia_lookup(path):
    h1 = httplib.HTTPConnection("www.archive.org")

    for attempt in range(5):
        h1.request("GET", path)
        res = h1.getresponse()
        res.read()
        #print (res.status, res.reason)
        if res.status != 200:
            break
    assert res.status == 302
    new_url = res.getheader('location')

    re_new_url = re.compile('^http://([^/]+\.us\.archive\.org)(/.+)$')

    m = re_new_url.match(new_url)
    return m.groups()

class snippets(delegate.page):
    path = '/search/inside/(.+)'
    def GET(self, ia):
        def find_matches(ia, q):
            host, ia_path = ia_lookup('/download/' + ia)
            url = 'http://' + host + '/~edward/inside.php?path=' + ia_path + '&q=' + web.urlquote(q)
            print url
            return simplejson.load(urllib.urlopen(url))
        return render_template('search/snippets.tmpl', find_matches, ia)
