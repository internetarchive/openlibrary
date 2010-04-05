
import web, re, urllib
from lxml.etree import parse, tostring, XML, XMLSyntaxError
from infogami.utils import delegate
from infogami import config
from openlibrary.catalog.utils import flip_name
from infogami.utils import view, template
from infogami.utils.view import safeint
import simplejson as json

try:
    from openlibrary.plugins.upstream.utils import get_coverstore_url, render_template
except AttributeError:
    pass # unittest
from openlibrary.plugins.search.code import search as _edition_search
from infogami.plugins.api.code import jsonapi

class edition_search(_edition_search):
    path = "/search/edition"

if hasattr(config, 'plugin_worksearch'):
    solr_host = config.plugin_worksearch.get('solr')
    solr_select_url = "http://" + solr_host + "/solr/works/select"

    solr_subject_host = config.plugin_worksearch.get('subject_solr')
    solr_subject_select_url = "http://" + solr_subject_host + "/solr/subjects/select"

    solr_author_host = config.plugin_worksearch.get('author_solr')
    solr_author_select_url = "http://" + solr_author_host + "/solr/authors/select"

    default_spellcheck_count = config.plugin_worksearch.get('spellcheck_count', 10)

to_drop = set(''';/?:@&=+$,<>#%"{}|\\^[]`\n\r''')

def str_to_key(s):
    return ''.join(c if c != ' ' else ' ' for c in s.lower() if c not in to_drop)

re_author_facet = re.compile('^(OL\d+A) (.*)$')
def read_author_facet(af):
    if '\t' in af:
        return af.split('\t')
    else:
        return re_author_facet.match(af).groups()

render = template.render

search_fields = ["key", "redirects", "title", "subtitle", "alternative_title", "alternative_subtitle", "edition_key", "by_statement", "publish_date", "lccn", "ia", "oclc", "isbn", "contributor", "publish_place", "publisher", "first_sentence", "author_key", "author_name", "author_alternative_name", "subject", "person", "place", "time"]

all_fields = search_fields + ["has_fulltext", "title_suggest", "edition_count", "publish_year", "language", "number_of_pages", "ia_count", "publisher_facet", "author_facet", "first_publish_year"] 

facet_fields = ["has_fulltext", "author_facet", "language", "first_publish_year", "publisher_facet", "subject_facet", "person_facet", "place_facet", "time_facet"]

facet_list_fields = [i for i in facet_fields if i not in ("has_fulltext")]

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
        if name == 'has_fulltext': # boolean facets
            e_true = e_lst.find("int[@name='true']")
            true_count = e_true.text if e_true is not None else 0
            e_false = e_lst.find("int[@name='false']")
            false_count = e_false.text if e_false is not None else 0
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
                k, display = read_author_facet(k) # FIXME
            elif name == 'language':
                display = get_language_name(k)
            else:
                display = k
            facets[name].append((k, display, e.text))
    return facets

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

def advanced_to_simple(params):
    q_list = []
    q = params.get('q', None)
    if q and q != '*:*':
        q_list.append(params['q'])
    for k in 'title', 'author':
        if k in params:
            q_list.append("%s:(%s)" % (k, params[k]))
    return ' '.join(q_list)

re_paren = re.compile('[()]')

def parse_query(params):
    q_list = []
    for k, v in params:
        v = v.strip()
        if k == 'q':
            q_list.append(v)
        if k == 'title':
            v = re_paren.sub(r'\\\1', v)
            q_list.append('title:(%s)' % v)
        if k == 'author':
            v = re_paren.sub(r'\\\1', v)
            q_list.append('author_name:(%s)' % v)
    return ' '.join(q_list)

re_isbn = re.compile('^([0-9]{9}[0-9X]|[0-9]{13})$')

def read_isbn(s):
    s = s.replace('-', '')
    return s if re_isbn.match(s) else None

re_fields = re.compile('(' + '|'.join(all_fields) + r'):', re.L)
re_author_key = re.compile(r'(OL\d+A)')

def run_solr_query(param = {}, rows=100, page=1, sort=None, spellcheck_count=None):
    if spellcheck_count == None:
        spellcheck_count = default_spellcheck_count
    q_list = []
    if 'q' in param:
        q_param = param['q'].strip()
    else:
        q_param = None
    offset = rows * (page - 1)
    use_dismax = False
    if q_param:
        if q_param == '*:*' or re_fields.match(q_param):
            q_list.append(q_param)
        else:
            isbn = read_isbn(q_param)
            if isbn:
                q_list.append('isbn:(%s)' % isbn)
            else:
                q_list.append('(%s)' % q_param)
                use_dismax = True
    else:
        if 'author' in param:
            v = param['author'].strip()
            m = re_author_key.search(v)
            if m: # FIXME: 'OL123A OR OL234A'
                q_list.append('author_key:(' + m.group(1) + ')')
            else:
                q_list.append('(author_name:(' + v + ') OR author_alternative_name:(' + v + '))')

        check_params = ['title', 'publisher', 'isbn', 'oclc', 'lccn', 'contribtor', 'subject', 'place', 'person', 'time']
        q_list += ['%s:(%s)' % (k, param[k]) for k in check_params if k in param]

    if use_dismax:
        q = web.urlquote(' '.join(q_list))
        solr_select = solr_select_url + "?version=2.2&defType=dismax&q.op=AND&q=%s&qf=text+title^5+author_name^5&bf=sqrt(edition_count)^10&start=%d&rows=%d&fl=key,author_name,author_key,title,subtitle,edition_count,ia,has_fulltext,first_publish_year,cover_edition_key&qt=standard&wt=standard&spellcheck=true&spellcheck.count=%d" % (q, offset, rows, spellcheck_count)
    else:
        q = web.urlquote(' '.join(q_list + ['_val_:"sqrt(edition_count)"^10']))
        solr_select = solr_select_url + "?version=2.2&q.op=AND&q=%s&start=%d&rows=%d&fl=key,author_name,author_key,title,subtitle,edition_count,ia,has_fulltext,first_publish_year,cover_edition_key&qt=standard&wt=standard&spellcheck=true&spellcheck.count=%d" % (q, offset, rows, spellcheck_count)
    solr_select += "&facet=true&" + '&'.join("facet.field=" + f for f in facet_fields)

    k = 'has_fulltext'
    if k in param:
        v = param[k].lower()
        if v not in ('true', 'false'):
            del param[k]
        param[k] == v
        solr_select += '&fq=%s:%s' % (k, v)

    for k in facet_list_fields:
        if k == 'author_facet':
            k = 'author_key'
        if k not in param:
            continue
        v = param[k]
        solr_select += ''.join('&fq=%s:"%s"' % (k, url_quote(l)) for l in v if l)
    if sort:
        solr_select += "&sort=" + url_quote(sort)
    reply = urllib.urlopen(solr_select).read()
    return (reply, solr_select, q_list)

re_pre = re.compile(r'<pre>(.*)</pre>', re.S)

def do_search(param, sort, page=1, rows=100, spellcheck_count=None):
    (reply, solr_select, q_list) = run_solr_query(param, rows, page, sort, spellcheck_count)
    is_bad = False
    if reply.startswith('<html'):
        is_bad = True
    if not is_bad:
        try:
            root = XML(reply)
        except XMLSyntaxError:
            is_bad = True
    if is_bad:
        m = re_pre.search(reply)
        return web.storage(
            facet_counts = None,
            docs = [],
            is_advanced = bool(param.get('q', 'None')),
            num_found = None,
            solr_select = solr_select,
            q_list = q_list,
            error = (web.htmlunquote(m.group(1)) if m else reply),
        )

    spellcheck = root.find("lst[@name='spellcheck']")
    spell_map = {}
    if spellcheck is not None and len(spellcheck):
        for e in spellcheck.find("lst[@name='suggestions']"):
            assert e.tag == 'lst'
            a = e.attrib['name']
            if a in spell_map:
                continue
            spell_map[a] = [i.text for i in e.find("arr[@name='suggestion']")]

    docs = root.find('result')
    return web.storage(
        facet_counts = read_facets(root),
        docs = docs,
        is_advanced = bool(param.get('q', 'None')),
        num_found = (int(docs.attrib['numFound']) if docs is not None else None),
        solr_select = solr_select,
        q_list = q_list,
        error = None,
        spellcheck = spell_map,
    )

def get_doc(doc):
    e_ia = doc.find("arr[@name='ia']")
    first_pub = None
    e_first_pub = doc.find("int[@name='first_publish_year']")
    if e_first_pub is not None:
        first_pub = e_first_pub.text

    work_subtitle = None
    e_subtitle = doc.find("str[@name='subtitle']")
    if e_subtitle is not None:
        work_subtitle = e_subtitle.text

    if doc.find("arr[@name='author_key']") is None:
        assert doc.find("arr[@name='author_name']") is None
        authors = []

    else:
        ak = [e.text for e in doc.find("arr[@name='author_key']")]
        an = [e.text for e in doc.find("arr[@name='author_name']")]
        authors = [(i, tidy_name(j)) for i, j in zip(ak, an)]
    cover = doc.find("str[@name='cover_edition_key']")

    return web.storage(
        key = doc.find("str[@name='key']").text,
        title = doc.find("str[@name='title']").text,
        edition_count = int(doc.find("int[@name='edition_count']").text),
        ia = [e.text for e in (e_ia if e_ia is not None else [])],
        authors = authors,
        first_publish_year = first_pub,
        subtitle = work_subtitle,
        cover_edition_key = (cover.text if cover is not None else None),
    )

re_subject_types = re.compile('^(places|times|people)/(.*)')
subject_types = {
    'places': 'place',
    'times': 'time',
    'people': 'person',
    'subjects': 'subject',
}

re_year_range = re.compile('^(\d{4})-(\d{4})$')

def work_object(w):
    obj = dict(
        authors = [web.storage(key='/authors/' + k, name=n) for k, n in zip(w['author_key'], w['author_name'])],
        edition_count = w['edition_count'],
        key = '/works/' + w['key'],
        title = w['title'],
        cover_edition_key = w.get('cover_edition_key', None),
        first_publish_year = (w['first_publish_year'] if 'first_publish_year' in w else None),
        ia = w.get('ia', [])
    )
    for f in 'has_fulltext', 'subtitle':
        if w.get(f, None):
            obj[f] = w[f]
    return web.storage(obj)

def get_facet(facets, f, limit=None):
    return list(web.group(facets[f][:limit * 2] if limit else facets[f], 2))
    
SUBJECTS = [
    web.storage(name="subject", key="subjects", prefix="/subjects/", facet="subject_facet", facet_key="subject_key"),
    web.storage(name="person", key="people", prefix="/subjects/people/", facet="person_facet", facet_key="person_key"),
    web.storage(name="place", key="places", prefix="/subjects/places/", facet="place_facet", facet_key="place_key"),
    web.storage(name="time", key="times", prefix="/subjects/times/", facet="time_facet", facet_key="time_key"),
]

def finddict(dicts, **filters):
    """Find a dictionary that matches given filter conditions.
    
        >>> dicts = [{"x": 1, "y": 2}, {"x": 3, "y": 4}]
        >>> finddict(dicts, x=1)
        {'x': 1, 'y': 2}
    """
    for d in dicts:
        if (all(d.get(k) == v for k, v in filters.iteritems())):
            return d            

def first(seq):
    try:
        return iter(seq).next()
    except:
        return None

def get_subject(key, details=False, offset=0, limit=12, **filters):
    """Returns data related to a subject.

    By default, it returns a storage object with key, name, work_count and works. 
    The offset and limit arguments are used to get the works.
        
        >>> get_subject("/subjects/Love") #doctest: +SKIP
        {
            "key": "/subjects/Love", 
            "name": "Love",
            "work_count": 5129, 
            "works": [...]
        }
        
    When details=True, facets and ebook_count are additionally added to the result.

    >>> get_subject("/subjects/Love", details=True) #doctest: +SKIP
    {
        "key": "/subjects/Love", 
        "name": "Love",
        "work_count": 5129, 
        "works": [...],
        "ebook_count": 94, 
        "authors": [
            {
                "count": 11, 
                "name": "Plato.", 
                "key": "/authors/OL12823A"
            }, 
            ...
        ],
        "subjects": [
            {
                "count": 1168,
                "name": "Religious aspects", 
                "key": "/subjects/religious aspects"
            }, 
            ...
        ],
        "times": [...],
        "places": [...],
        "people": [...],
        "publishing_history": [[1492, 1], [1516, 1], ...],
        "publishers": [
            {
                "count": 57, 
                "name": "Sine nomine"        
            },
            ...
        ]
    }
    
    Optional arguments limit and offset can be passed to limit the number of works returned and starting offset.
    
    Optional arguments has_fulltext and published_in can be passed to filter the results.
    """
    m = web.re_compile(r'/subjects/(places/|times/|people/|)(.+)').match(key)
    if m:
        prefix = "/subjects/" + m.group(1)
        path = m.group(2)
    else:
        return None
        
    meta = finddict(SUBJECTS, prefix=prefix)
    
    q = {meta.facet_key: str_to_key(path).lower()}
    subject_type = meta.name

    name = path.replace("_", " ")

    def facet_wrapper(facet, value, count):
        if facet == "publish_year":
            return [int(value), count]
        elif facet == "publisher_facet":
            return web.storage(name=value, count=count)
        elif facet == "author_facet":
            author = read_author_facet(value) # FIXME
            return web.storage(name=author[1], key="/authors/" + author[0], count=count)
        elif facet in ["subject_facet", "person_facet", "place_facet", "time_facet"]:
            return web.storage(key=finddict(SUBJECTS, facet=facet).prefix + str_to_key(value).replace(" ", "_"), name=value, count=count)
        elif facet == "has_fulltext":
            return [value, count]
        else:
            return web.storage(name=value, count=count)

    # search for works
    from search import work_search
    kw = {} 
    if details:
        kw['facets'] = [
            {"name": "author_facet", "sort": "count"},
            "language", 
            "publisher_facet", 
            {"name": "publish_year", "limit": -1}, 
            "subject_facet", "person_facet", "place_facet", "time_facet", 
            "has_fulltext"]        
        kw['facet.mincount'] = 1
        kw['facet.limit'] = 25
        kw['facet_wrapper'] = facet_wrapper

    if filters:
        if filters.get("has_fulltext") == "true":
            q['has_fulltext'] = "true"
        if filters.get("publish_year"):
            q['publish_year'] = filters['publish_year']

    result = work_search(q, offset=offset, limit=limit, sort="edition_count desc", **kw)
    for w in result.docs:
        w.ia = w.ia and w.ia[0] or None

    subject = web.storage(
        key=key,
        name=name,
        subject_type=subject_type,
        work_count = result['num_found'],
        works=result['docs']
    )

    if details:
        subject.ebook_count = dict(result.facets["has_fulltext"]).get("true", 0)

        subject.subjects = result.facets["subject_facet"]
        subject.places = result.facets["place_facet"]
        subject.people = result.facets["person_facet"]
        subject.times = result.facets["time_facet"]

        subject.authors = result.facets["author_facet"]        
        subject.publishers = result.facets["publisher_facet"]
        
        subject.publishing_history = [[year, count] for year, count in result.facets["publish_year"] if year > 1000]
        
        # strip self from subjects and use that to find exact name
        for i, s in enumerate(subject[meta.key]):
            if s.key.lower() == key.lower():
                subject.name = s.name;
                subject[meta.key].pop(i)
                break

    return subject

class subjects_json(delegate.page):
    path = '(/subjects/.+)'
    encoding = "json"

    @jsonapi
    def GET(self, key):
        if key.lower() != key:
            raise web.redirect(key.lower())

        i = web.input(offset=0, limit=12, details="false", has_fulltext="false")

        filters = {}
        if i.get("has_fulltext") == "true":
            filters["has_fulltext"] = "true"
            
        if i.get("published_in"):
            if "-" in i.published_in:
                begin, end = i.published_in.split("-", 1)
                
                if safeint(begin, None) is not None and safeint(end, None) is not None:
                    filters["publish_year"] = [begin, end]
            else:
                y = safeint(i.published_in, None)
                if y is not None:
                    filters["publish_year"] = i.published_in

        i.limit = safeint(i.limit, 12)
        i.offset = safeint(i.offset, 0)

        subject = get_subject(key, offset=i.offset, limit=i.limit, details=i.details.lower() == "true", **filters)
        return json.dumps(subject)
    
class subjects(delegate.page):
    path = '(/subjects/.+)'
    
    def GET(self, key):
        if key.lower() != key:
            raise web.redirect(key.lower())
            
        page = get_subject(key, details=True)
        
        if page.work_count == 0:
            return render_template('subjects/notfound.tmpl', key)
        
        return render_template("subjects", page)
        
class search(delegate.page):
    def clean_inputs(self, i):
        params = {}
        need_redirect = False
        for k, v in i.items():
            if isinstance(v, list):
                if v == []:
                    continue
                clean = [b.strip() for b in v]
                if clean != v:
                    need_redirect = True
                if len(clean) == 1 and clean[0] == u'':
                    clean = None
            else:
                clean = v.strip()
                if clean == '':
                    need_redirect = True
                    clean = None
                if clean != v:
                    need_redirect = True
            params[k] = clean
        return params if need_redirect else None

    def GET(self):
        i = web.input(author_key=[], language=[], first_publish_year=[], publisher_facet=[], subject_facet=[], person_facet=[], place_facet=[], time_facet=[])
        params = self.clean_inputs(i)

        if params:
            raise web.seeother(web.changequery(**params))

        return render.work_search(i, do_search, get_doc)

def works_by_author(akey, sort='editions', page=1, rows=100):
    q='author_key:' + akey
    offset = rows * (page - 1)
    solr_select = solr_select_url + "?version=2.2&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=key,author_name,author_key,title,subtitle,edition_count,ia,cover_edition_key,has_fulltext,first_publish_year&qt=standard&wt=json" % (q, offset, rows)
    facet_fields = ["author_facet", "language", "publish_year", "publisher_facet", "subject_facet", "person_facet", "place_facet", "time_facet"]
    if sort == 'editions':
        solr_select += '&sort=edition_count+desc'
    elif sort.startswith('old'):
        solr_select += '&sort=first_publish_year+asc'
    elif sort.startswith('new'):
        solr_select += '&sort=first_publish_year+desc'
    elif sort.startswith('title'):
        solr_select += '&sort=title+asc'
    solr_select += "&facet=true&facet.mincount=1&f.author_facet.facet.sort=count&f.publish_year.facet.limit=-1&facet.limit=25&" + '&'.join("facet.field=" + f for f in facet_fields)
    reply = json.load(urllib.urlopen(solr_select))
    facets = reply['facet_counts']['facet_fields']
    works = [work_object(w) for w in reply['response']['docs']]

    def get_facet(f, limit=None):
        return list(web.group(facets[f][:limit * 2] if limit else facets[f], 2))

    return web.storage(
        num_found = int(reply['response']['numFound']),
        works = works,
        years = [(int(k), v) for k, v in get_facet('publish_year')],
        get_facet = get_facet,
        sort = sort,
    )

def sorted_work_editions(wkey, json_data=None):
    q='key:' + wkey
    if not json_data: # for testing
        solr_select = solr_select_url + "?version=2.2&q.op=AND&q=%s&rows=10&fl=edition_key&qt=standard&wt=json" % q
        json_data = urllib.urlopen(solr_select).read()
    reply = json.loads(json_data)

    if reply['response']['numFound'] == 0:
        return []
    return reply["response"]['docs'][0].get('edition_key', [])

def simple_search(q, offset=0, rows=20, sort=None):
    solr_select = solr_select_url + "?version=2.2&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=*%%2Cscore&qt=standard&wt=json" % (web.urlquote(q), offset, rows)
    if sort:
        solr_select += "&sort=" + web.urlquote(sort)

    return json.load(urllib.urlopen(solr_select))

def top_books_from_author(akey, rows=5, offset=0):
    q = 'author_key:(' + akey + ')'
    solr_select = solr_select_url + "?indent=on&version=2.2&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=*%%2Cscore&qt=standard&wt=standard&explainOther=&hl=on&hl.fl=title" % (q, offset, rows)
    solr_select += "&sort=edition_count+desc"

    reply = urllib.urlopen(solr_select)
    root = parse(reply).getroot()
    result = root.find('result')
    if result is None:
        return []

    books = [web.storage(
        key=doc.find("str[@name='key']").text,
        title=doc.find("str[@name='title']").text,
        edition_count=int(doc.find("int[@name='edition_count']").text),
    ) for doc in result]

    return { 'books': books, 'total': int(result.attrib['numFound']) }

def do_merge():
    return

class merge_authors(delegate.page):
    path = '/merge/authors'
    def GET(self):
        i = web.input(key=[], master=None)
        keys = []
        for key in i.key:
            if key not in keys:
                keys.append(key)
        errors = []
        if i.master == '':
            errors += ['you must select a master author record']
        if not keys:
            errors += ['no authors selected']

        if not errors and i.master:
            master_key = '/authors/' + i.master
            assert web.ctx.site.get(master_key)['type']['key'] == '/type/author'
            old_keys = set(k for k in keys if k != i.master) 
            for old in old_keys:
                q = {'type': '/type/work', 'authors': {'author': '/authors/' + old}}
                work_keys = web.ctx.site.things(q)

            return 'merged'

        return render['merge/authors'](errors, i.master, keys, \
            top_books_from_author, do_merge)

class improve_search(delegate.page):
    def GET(self):
        i = web.input(q=None)
        boost = dict((f, i[f]) for f in search_fields if f in i)
        return render.improve_search(search_fields, boost, i.q, simple_search)

class merge_author_works(delegate.page):
    path = "/authors/(OL\d+A)/merge-works"
    def GET(self, key):
        works = works_by_author(key)
    
class subject_search(delegate.page):
    path = '/search/subjects'
    def GET(self):
        def get_results(q, offset=0, limit=100):
            solr_select = solr_subject_select_url + "?q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=name,type,count&qt=standard&wt=json" % (web.urlquote(q), offset, limit)
            solr_select += '&sort=count+desc'
            return json.loads(urllib.urlopen(solr_select).read())
        return render_template('search/subjects.tmpl', get_results)

class author_search(delegate.page):
    path = '/search/authors'
    def GET(self):
        def get_results(q, offset=0, limit=100):
            solr_select = solr_author_select_url + "?q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=*&qt=standard&wt=json" % (web.urlquote(q), offset, limit)
            solr_select += '&sort=work_count+desc'
            return json.loads(urllib.urlopen(solr_select).read())
        return render_template('search/authors.tmpl', get_results)

class search_json(delegate.page):
    path = "/search"
    encoding = "json"
    
    def GET(self):
        i = web.input()
        if 'query' in i:
            query = simplejson.loads(i.query)
        else:
            query = i
        
        from openlibrary.utils.solr import Solr
        import simplejson
        
        solr = Solr("http://%s/solr/works" % solr_host)
        result = solr.select(query)
        web.header('Content-Type', 'application/json')
        return delegate.RawText(simplejson.dumps(result, indent=True))
