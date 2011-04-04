from infogami.utils import delegate, stats
from infogami.utils.view import render_template, public
from infogami import config
from lxml import etree
from openlibrary.utils import escape_bracket

import re, web, urllib, simplejson, httplib

re_query_parser_error = re.compile(r'<pre>([^<]+?)</pre>', re.S)
re_inside_fields = re.compile(r'(ia|body|page_count|body_length):')
bad_fields = ['title', 'author', 'authors', 'lccn', 'ia', 'oclc', 'isbn', 'publisher', 'subject', 'person', 'place', 'time']
re_bad_fields = re.compile(r'\b(' + '|'.join(bad_fields) + '):')

def escape_q(q):
    if re_inside_fields.match(q):
        return q
    return escape_bracket(q).replace(':', '\\:')

trans = { '\n': '<br>', '{{{': '<b>', '}}}': '</b>', }
re_trans = re.compile(r'(\n|\{\{\{|\}\}\})')
def quote_snippet(snippet):
    return re_trans.sub(lambda m: trans[m.group(1)], web.htmlquote(snippet))

if hasattr(config, 'plugin_inside'):
    solr_host = config.plugin_inside['solr']
    solr_select_url = "http://" + solr_host + "/solr/inside/select"

def editions_from_ia(ia):
    q = {'type': '/type/edition', 'ocaid': ia, 'title': None, 'covers': None, 'works': None, 'authors': None}
    editions = web.ctx.site.things(q)
    if not editions:
        del q['ocaid']
        q['source_records'] = 'ia:' + ia
        editions = web.ctx.site.things(q)
    return editions

def read_from_archive(ia):
    meta_xml = 'http://www.archive.org/download/' + ia + '/' + ia + '_meta.xml'
    stats.begin("archive.org", url=meta_xml)
    xml_data = urllib.urlopen(meta_xml)
    item = {}
    try:
        tree = etree.parse(xml_data)
    except etree.XMLSyntaxError:
        return {}
    finally:
        stats.end()
    root = tree.getroot()

    fields = ['title', 'creator', 'publisher', 'date', 'language']

    for k in 'title', 'date', 'publisher':
        v = root.find(k)
        if v is not None:
            item[k] = v.text

    for k in 'creator', 'language', 'collection':
        v = root.findall(k)
        if len(v):
            item[k] = [i.text for i in v if i.text]
    return item

@public
def search_inside_result_count(q):
    q = escape_q(q)
    solr_select = solr_select_url + "?fl=ia&q.op=AND&wt=json&q=" + web.urlquote(q)
    stats.begin("solr", url=solr_select)
    json_data = urllib.urlopen(solr_select).read()
    stats.end()
    try:
        results = simplejson.loads(json_data)
    except:
        return None
    return results['response']['numFound']

class search_inside(delegate.page):
    path = '/search/inside'

    def GET(self):
        def get_results(q, offset=0, limit=100, snippets=3, fragsize=200):
            m = re_bad_fields.match(q)
            if m:
                return { 'error': m.group(1) + ' search not supported' }
            q = escape_q(q)
            solr_select = solr_select_url + "?fl=ia,body_length,page_count&hl=true&hl.fl=body&hl.snippets=%d&hl.mergeContiguous=true&hl.usePhraseHighlighter=false&hl.simple.pre={{{&hl.simple.post=}}}&hl.fragsize=%d&q.op=AND&q=%s&start=%d&rows=%d&qf=body&qt=standard&hl.maxAnalyzedChars=1000000&wt=json" % (snippets, fragsize, web.urlquote(q), offset, limit)
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
        if res.status != 200:
            break
    assert res.status == 302
    new_url = res.getheader('location')

    re_new_url = re.compile('^http://([^/]+\.us\.archive\.org)(/.+)$')

    m = re_new_url.match(new_url)
    return m.groups()

re_h1_error = re.compile('<center><h1>(.+?)</h1></center>')

class snippets(delegate.page):
    path = '/search/inside/(.+)'
    def GET(self, ia):
        def find_matches(ia, q):
            q = escape_q(q)
            host, ia_path = ia_lookup('/download/' + ia)
            url = 'http://' + host + '/fulltext/inside.php?item_id=' + ia + '&doc=' + ia + '&path=' + ia_path + '&q=' + web.urlquote(q)
            ret = urllib.urlopen(url)
            try:
                return simplejson.load(ret)
            except:
                m = re_h1_error.search(ret)
                return { 'error': web.htmlunquote(m.group(1)) }
        return render_template('search/snippets.tmpl', find_matches, ia)
