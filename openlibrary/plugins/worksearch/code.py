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

facet_fields = ["has_fulltext", "author_facet", "language", "first_publish_year", "publisher_facet", "fiction", "subject_facet", "person_facet", "place_facet", "time_facet"]

facet_list_fields = [i for i in facet_fields if i not in ("has_fulltext", "fiction")]

def get_language_name(code):
    l = web.ctx.site.get('/languages/' + code)
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
            elif name == 'language':
                display = get_language_name(k)
            else:
                display = k
            facets[name].append((k, display, e.text))
    return facets

def get_search_url(params, exclude = None):
    assert params
    def process(exclude = None):
        url = []
        for k, v in params.items():
            for i in v if isinstance(v, list) else [v]:
                if exclude and (k, i) == exclude:
                    continue
                url.append(k + "=" + i)
        ret = '?' + '&'.join(url)
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

re_isbn = re.compile('^([0-9]{9}[0-9X]|[0-9]{13})$')

def read_isbn(s):
    s = s.replace('-', '')
    return s if re_isbn.match(s) else None

re_fields = re.compile('(' + '|'.join(all_fields) + r'):', re.L)
re_author_key = re.compile(r'(OL\d+A)')

def run_solr_query(param = {}, rows=100, page=1, sort_by_edition_count=True):
    q_list = []
    if 'q' in param:
        q_param = param['q'].strip()
    else:
        q_param = None
    offset = rows * (page - 1)
    query_params = dict((k, url_quote(param[k])) for k in ('title', 'publisher', 'isbn', 'oclc', 'lccn', 'first_sentence', 'contribtor', 'author') if k in param)
    if q_param:
        if q_param == '*:*' or re_fields.match(q_param):
            q_list.append(q_param)
        else:
            isbn = read_isbn(q_param)
            if isbn:
                q_list.append('isbn:(%s)' % isbn)
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

    solr_select = solr_select_url + "?version=2.2&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=key,doc.author_name,doc.author_key,title,edition_count,ia&qt=standard&wt=standard" % (q, offset, rows)
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
    return (parse(reply).getroot(), search_url, solr_select, q_list)

def do_search(param, sort, page=1, rows=100):
    (root, search_url, solr_select, q_list) = run_solr_query(param, True, rows, page, sort != 'score')
    docs = root.find('result')
    return web.storage(
        facet_counts = read_facets(root),
        docs = docs,
        is_advanced = bool(param[q]),
        num_found = (int(docs.attrib['numFound']) if docs is not None else None),
        search_url = search_url,
        solr_select = solr_select,
        q_list = q_list,
    )

def get_doc(doc):
    e_ia = doc.find("arr[@name='ia']")

    ak = [e.text for e in doc.find("arr[@name='author_key']")]
    an = [e.text for e in doc.find("arr[@name='author_name']")]

    return web.storage(
        key = doc.find("str[@name='key']").text,
        title = doc.find("str[@name='title']").text,
        edition_count = int(doc.find("int[@name='edition_count']").text),
        ia = [e.text for e in (e_ia if e_ia is not None else [])],
        authors = [(i, tidy_name(j)) for i, j in zip(ak, an)],
    )

class search(delegate.page):
    def GET(self):
        input = web.input(author_key=[], language=[], first_publish_year=[], publisher_facet=[], subject_facet=[], person_facet=[], place_facet=[], time_facet=[])

        return render.work_search(input, do_search, get_doc)
