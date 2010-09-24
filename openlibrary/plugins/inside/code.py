from infogami.utils import delegate, stats
from infogami.utils.view import render_template

import re, web, urllib, simplejson

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

class subject_search(delegate.page):
    path = '/search/inside'

    def GET(self):
        def get_results(q, offset=0, limit=100, snippts=3, fragsize=200):
            q = escape_bracket(q)
            solr_select = solr_select_url + "?fl=ia,body_length,page_count&hl=true&hl.fl=body&hl.snippets=%d&hl.mergeContiguous=true&hl.usePhraseHighlighter=true&hl.simple.pre={{{&hl.simple.post=}}}&hl.fragsize=%d&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=*&qt=standard&wt=json" % (snippts, fragsize, web.urlquote(q), offset, limit)
            stats.begin("solr", url=solr_select)
            json_data = urllib.urlopen(solr_select).read()
            stats.end()
            return simplejson.loads(json_data)

        return render_template('search/inside.tmpl', get_results, quote_snippet, editions_from_ia)

