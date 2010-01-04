import web, re, urllib
from lxml.etree import parse, tostring
from infogami.utils import delegate
from infogami import config
from openlibrary.catalog.utils import flip_name
from infogami.utils import view, template

solr_host = config.plugin_worksearch.get('solr')
solr_select_url = "http://" + solr_host + "/solr/works/select"

render = template.render

search_fields = ["key", "redirects", "title", "subtitle", "alternative_title", "alternative_subtitle", "edition_key", "by_statement", "publish_date", "lccn", "ia", "oclc", "isbn", "contributor", "publish_place", "publisher", "first_sentence", "author_key", "author_name", "author_alternative_name", "subject", "person", "place", "time"]

all_fields = search_fields + ["has_fulltext", "title_suggest", "edition_count", "publish_year", "language", "number_of_pages", "ia_count", "publisher_facet", "author_facet", "fiction", "first_publish_year"] 

facet_fields = ["has_fulltext", "author_facet", "language", "first_publish_year", "publisher_facet", "fiction", "subject", "person", "place", "time"]

facet_list_fields = [i for i in facet_fields if i not in ("has_fulltext", "fiction")]

trans = {'&':'amp','<':'lt','>':'gt', '"': 'quot'}
re_html_replace = re.compile('([&<>"])')

def esc(s):
    if not isinstance(s, basestring):
        return s
    return re_html_replace.sub(lambda m: "&%s;" % trans[m.group(1)], s)

def esc_and_truncate(s, length=60):
    if len(s) < length:
        return esc(s)
    return esc(s[:length]) + '&hellip;'

def get_language_name(code):
    l = web.ctx.site.get('/l/' + code)
    return l.name if l else "'%s' unknown" % code

def read_facets(root):
    bool_map = dict(true='yes', false='no')
    e_facet_counts = root.find("lst[@name='facet_counts']")
    e_facet_fields = e_facet_counts.find("lst[@name='facet_fields']")
    facets = {}
    for e_lst in e_facet_fields:
        assert e_lst.tag == 'lst'
        name = e_lst.attrib['name']
        if name == 'author_facet':
            name = 'author_key'
        if name in ('fiction', 'has_fulltext'): # boolean facets
            true_count = e_lst.find("int[@name='true']").text
            false_count = e_lst.find("int[@name='false']").text
            facets[name] = [
                ('true', 'yes', true_count),
                ('false', 'no', false_count),
            ]
            continue
        facets[name] = []
        for e in e_lst:
            if e.text == '0':
                continue
            k = e.attrib['name']
            if name == 'author_key':
                k, display = eval(k)
                k = k[3:] # /a/OL123A -> OL123A
            elif name == 'language':
                display = get_language_name(k)
            else:
                display = k
            facets[name].append((k, display, e.text))
    return facets

def get_search_url(params, exclude = None):
    assert params
    print 'params:', params
    def process(exclude = None):
        url = []
        for k, v in params.items():
            for i in v if isinstance(v, list) else [v]:
                if exclude and (k, i) == exclude:
                    continue
                url.append(k + "=" + i)
        ret = '?' + '&'.join(url)
        if exclude:
            print exclude
            print ret
        return ret
    return process



def url_quote(s):
    if not s:
        return ''
    return urllib.quote_plus(s.encode('utf-8'))

re_baron = re.compile(r'^([A-Z][a-z]+), (.+) \1 Baron$')
def tidy_name(s):
    if s is None:
        return '<em>name missing</em>'
    if s == 'Mao, Zedong':
        return 'Mao Zedong'
    m = re_baron.match(s)
    if m:
        return m.group(2) + ' ' + m.group(1)
    if ' Baron ' in s:
        s = s[:s.find(' Baron ')]
    elif s.endswith(' Sir'):
        s = s[:-4]
    return flip_name(s)

def read_highlight(root):
    e_highlight = root.find("lst[@name='highlighting']")
    highlight_titles = {}
    for e_lst in e_highlight:
        if len(e_lst) == 0:
            continue
        e_arr = e_lst[0]
        e_str = e_arr[0]
        assert e_lst.tag == 'lst' and len(e_lst) == 1 \
            and e_arr.tag == 'arr' and e_arr.attrib['name'] == 'title' and len(e_arr) == 1 \
            and e_str.tag == 'str'
        work_key = e_lst.attrib['name']
        highlight_titles[work_key] = e_str.text.replace('em>','b>')
    return highlight_titles

re_fields = re.compile('(' + '|'.join(all_fields) + r'):', re.L)
re_author_key = re.compile(r'(OL\d+A)')

def run_solr_query(param = {}, facets=True, rows=100, page=1, sort_by_edition_count=True):
    q_list = []
    q_param = param.get('q', None)
    offset = rows * (page - 1)
    query_params = dict((k, url_quote(param[k])) for k in ('title', 'publisher', 'isbn', 'oclc', 'lccn', 'first_sentence', 'contribtor', 'author') if k in param)
    if q_param:
        if q_param == '*:*' or re_fields.match(q_param):
            q_list.append(q_param)
        else:
            q_list.append('(' + ' OR '.join('%s:(%s)' % (f, q_param) for f in search_fields) + ')')
        query_params['q'] = url_quote(q_param)
    else:
        if 'author' in param:
            v = param['author'].strip()
            m = re_author_key.search(v)
            if m: # FIXME: 'OL123A OR OL234A'
                q_list.append('author_key:(' + m.group(1) + ')')
            else:
                q_list.append('author_name:(' + v + ')')

        q_list += ['%s:(%s)' % (k, param[k]) for k in 'title', 'publisher', 'isbn', 'oclc', 'lccn', 'first_sentence', 'contribtor' if k in param]
    q_list += ['%s:(%s)' % (k, param[k]) for k in 'has_fulltext', 'fiction' if k in param]

    q = url_quote(' AND '.join(q_list))

    solr_select = solr_select_url + "?indent=on&version=2.2&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=*%%2Cscore&qt=standard&wt=standard&explainOther=&hl=on&hl.fl=title" % (q, offset, rows)
    if facets:
        solr_select += "&facet=true&" + '&'.join("facet.field=" + f for f in facet_fields)

    for k in 'has_fulltext', 'fiction':
        if k not in param:
            continue
        v = param[k].lower()
        if v not in ('true', 'false'):
            del param[k]
        param[k] == v
        query_params[k] = url_quote(v)
        solr_select += '&fq=%s:%s' % (k, v)

    for k in facet_list_fields:
        if k == 'author_facet':
            k = 'author_key'
        if k not in param:
            continue
        v = param[k]
        query_params[k] = [url_quote(i) for i in v]
        solr_select += ''.join('&fq=%s:"%s"' % (k, l) for l in v if l)
    if sort_by_edition_count:
        solr_select += "&sort=edition_count+desc"
    reply = urllib.urlopen(solr_select)
    search_url = get_search_url(query_params)
    return (parse(reply).getroot(), search_url, solr_select)

def search(param = {}, facets=True, rows=100, show_total=True):
    page = int(param.get('page', 1))
    sort = param.get('sort', None)
    (root, search_url, solr_select) = run_solr_query(param, facets, rows, page, sort != 'score')

    sort_url = search_url() # first page
    ret = 'Sort by: '

    if sort == 'score':
        ret += '<a href="%s">number of editions</a> OR <b>relevance</b>' % sort_url
    else:
        ret += '<b>number of editions</b> OR <a href="%s&sort=score">relevance</a>' % sort_url
    ret += '<p>\n'

    if 'debug' in param:
        ret += esc(solr_select) + '<br>\n'

    result = root.find('result')
    if result is None:
        return esc(solr_select) + '<br>no results found'

    num_found = int(result.attrib['numFound'])

    highlight_titles = read_highlight(root)

    if facets:
        facet_counts = read_facets(root)
        ret += '<table><tr><td valign="top">'
        ret += unicode(render.work_facets(facet_counts, param, search_url))
        ret += '</td><td>'

    if show_total:
        ret += 'Number found: %s<br>' % web.commify(num_found)
    ret += '<table>'
    ret += '<tr><td colspan="3" align="right">editions</td>'
    if facets and facet_counts['has_fulltext'][0][2] != '0':
        ret += '<td align="right">eBook?</td>'
    ret += '</tr>\n'
    for doc in result:
        # ret += doc_table(doc)
        # ret += '<pre>' + esc(tostring(highlight, pretty_print=True)) + '</pre>'
        work_key = doc.find("str[@name='key']").text
        title = highlight_titles[work_key] \
            if work_key in highlight_titles \
            else esc_and_truncate(doc.find("str[@name='title']").text)
        e_fs = doc.find("arr[@name='first_sentence']")
        first_sentences = [e.text for e in (e_fs if e_fs is not None else [])]
        fulltext = doc.find("bool[@name='has_fulltext']").text == 'true'
        edition_count = int(doc.find("int[@name='edition_count']").text)
        e_ia = doc.find("arr[@name='ia']")
        ia_list = [e.text for e in (e_ia if e_ia is not None else [])]
        author_key = []
        author_name = []
        for e_str in doc.find("arr[@name='author_key']"):
            assert e_str.tag == 'str'
            author_key.append('/authors/' + e_str.text)
        for e_str in doc.find("arr[@name='author_name']"):
            assert e_str.tag == 'str'
            author_name.append(e_str.text)
        authors = ', '.join('<a href="http://upstream.openlibrary.org%s">%s</a>' % (i, tidy_name(j)) for i, j in zip(author_key, author_name))
        #authors = ', '.join('<a href="http://upstream.openlibrary.org%s">%s</a> (<a href="?author=&quot;%s&quot;">search</a>)' % (i, tidy_name(j), j) for i, j in zip(author_key, author_name))
        ret += '<tr>'
        ret += u'<td><a href="http://upstream.openlibrary.org/works/%s">%s</a>' % (work_key, title)
        ret += '</td>'
        ret += '<td>by %s</td>' % authors
        ret += '<td align="right">%s</td>' % web.commify(edition_count)
        if fulltext:
            ret += '<td align="right">%s&nbsp;eBook%s</td>' % (web.commify(len(ia_list)), "s" if len(ia_list) != 1 else "")
        ret += '</tr>'
    ret += '</table>'
    if facets:
        ret += '</td></tr></table>'

    if page * rows < num_found:
        next_page_url = search_url() + ('&page=%d' % (page + 1,))

        ret += '<br><a href="%s">Next page</a>' % esc(next_page_url)
    return ret

def textfield(i, name):
    if i.get(name, None):
        return '<input name="%s" value="%s" size="30">' % (name, esc(i.get(name)))
    else:
        return '<input name="%s" size="30">' % name

class work_search(delegate.page):
    def GET(self):
        input = web.input(author_key=[], language=[], first_publish_year=[], publisher_facet=[], subject=[], person=[], place=[], time=[])
        param = {}
        for p in ['q', 'title', 'author', 'page', 'sort', 'isbn', 'oclc', 'contributor', 'publish_place', 'lccn', 'ia', 'first_sentence', 'publisher', 'author_key', 'debug'] + facet_fields:
            if p in input and input[p]:
                param[p] = input[p]

        results = search(param, facets=True) if param else ''
        return render.work_search(input, results)
