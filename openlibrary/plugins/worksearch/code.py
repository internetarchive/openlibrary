import web, re, urllib, dbm
from lxml.etree import XML, XMLSyntaxError
from infogami.utils import delegate, stats
from infogami import config
from infogami.utils.view import render, render_template, safeint, add_flash_message
import simplejson as json
from openlibrary.plugins.openlibrary.processors import urlsafe
from openlibrary.utils import str_to_key, url_quote
from unicodedata import normalize
from collections import defaultdict
import os

ftoken_db = None

try:
    from openlibrary.plugins.upstream.utils import get_coverstore_url
except AttributeError:
    pass # unittest
from openlibrary.plugins.search.code import search as _edition_search
from infogami.plugins.api.code import jsonapi

from openlibrary.core.models import Subject

re_solr_range = re.compile(r'\[.+\bTO\b.+\]', re.I)
re_bracket = re.compile(r'[\[\]]')
re_to_esc = re.compile(r'[\[\]:]')
def escape_bracket(q):
    if re_solr_range.search(q):
        return q
    return re_bracket.sub(lambda m:'\\'+m.group(), q)

class edition_search(_edition_search):
    path = "/search/edition"

if hasattr(config, 'plugin_worksearch'):
    solr_host = config.plugin_worksearch.get('solr', 'localhost')
    solr_select_url = "http://" + solr_host + "/solr/works/select"

    solr_subject_host = config.plugin_worksearch.get('subject_solr', 'localhost')
    solr_subject_select_url = "http://" + solr_subject_host + "/solr/subjects/select"

    solr_author_host = config.plugin_worksearch.get('author_solr', 'localhost')
    solr_author_select_url = "http://" + solr_author_host + "/solr/authors/select"

    solr_edition_host = config.plugin_worksearch.get('edition_solr', 'localhost')
    solr_edition_select_url = "http://" + solr_edition_host + "/solr/editions/select"

    default_spellcheck_count = config.plugin_worksearch.get('spellcheck_count', 10)

    ebook_count_host = config.plugin_worksearch.get('ebook_count_host')
    ebook_count_user = config.plugin_worksearch.get('ebook_count_user') or os.getenv("USER")
    ebook_count_db_name = config.plugin_worksearch.get('ebook_count_db_name')

    if ebook_count_host:
        ebook_count_db = web.database(dbn='postgres', db=ebook_count_db_name, host=ebook_count_host, user=ebook_count_user)
    else:
        ebook_count_db = web.database(dbn='postgres', db=ebook_count_db_name, user=ebook_count_user)

re_author_facet = re.compile('^(OL\d+A) (.*)$')
def read_author_facet(af):
    # example input: "OL26783A Leo Tolstoy"
    return re_author_facet.match(af).groups()

search_fields = ["key", "redirects", "title", "subtitle", "alternative_title", "alternative_subtitle", "edition_key", "by_statement", "publish_date", "lccn", "ia", "oclc", "isbn", "contributor", "publish_place", "publisher", "first_sentence", "author_key", "author_name", "author_alternative_name", "subject", "person", "place", "time"]

all_fields = search_fields + ["has_fulltext", "title_suggest", "edition_count", "publish_year", "language", "number_of_pages", "ia_count", "publisher_facet", "author_facet", "first_publish_year"] + ['%s_key' % f for f in ('subject', 'person', 'place', 'time')]

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
                k, display = read_author_facet(k)
            elif name == 'language':
                display = get_language_name(k)
            else:
                display = k
            facets[name].append((k, display, e.text))
    return facets

re_isbn = re.compile('^([0-9]{9}[0-9Xx]|[0-9]{13})$')

re_isbn_field = re.compile('^\s*(?:isbn[:\s]*)?([-0-9X]{9,})\s*$', re.I)

def read_isbn(s):
    s = s.replace('-', '')
    return s if re_isbn.match(s) else None

#re_field = re.compile('([a-zA-Z_]+):')
re_author_key = re.compile(r'(OL\d+A)')

field_name_map = {
    'author': 'author_name',
    'authors': 'author_name',
    'by': 'author_name',
    'publishers': 'publisher',
}

all_fields += field_name_map.keys()
re_fields = re.compile('(-?' + '|'.join(all_fields) + r'):', re.I)

plurals = dict((f + 's', f) for f in ('publisher', 'author'))

re_op = re.compile(' +(OR|AND)$')

def parse_query_fields(q):
    found = [(m.start(), m.end()) for m in re_fields.finditer(q)]
    first = q[:found[0][0]].strip() if found else q.strip()
    if first:
        yield {'field': 'text', 'value': first.replace(':', '\:')}
    for field_num in range(len(found)):
        op_found = None
        f = found[field_num]
        field_name = q[f[0]:f[1]-1].lower()
        if field_name in field_name_map:
            field_name = field_name_map[field_name]
        if field_num == len(found)-1:
            v = q[f[1]:].strip()
        else:
            v = q[f[1]:found[field_num+1][0]].strip()
            m = re_op.search(v)
            if m:
                v = v[:-len(m.group(0))]
                op_found = m.group(1)
        yield {'field': field_name, 'value': v.replace(':', '\:')}
        if op_found:
            yield {'op': op_found }

def build_q_list(param):
    q_list = []
    if 'q' in param:
        q_param = param['q'].strip()
    else:
        q_param = None
    use_dismax = False
    if q_param:
        if q_param == '*:*':
            q_list.append(q_param)
        elif 'NOT ' in q_param: # this is a hack
            q_list.append(q_param.strip())
        elif re_fields.search(q_param):
            q_list.extend(i['op'] if 'op' in i else '%s:(%s)' % (i['field'], i['value']) for i in parse_query_fields(q_param))
        else:
            isbn = read_isbn(q_param)
            if isbn:
                q_list.append('isbn:(%s)' % isbn)
            else:
                q_list.append(q_param.strip().replace(':', '\:'))
                use_dismax = True
    else:
        if 'author' in param:
            v = param['author'].strip()
            m = re_author_key.search(v)
            if m: # FIXME: 'OL123A OR OL234A'
                q_list.append('author_key:(' + m.group(1) + ')')
            else:
                v = re_to_esc.sub(lambda m:'\\' + m.group(), v)
                q_list.append('(author_name:(' + v + ') OR author_alternative_name:(' + v + '))')

        check_params = ['title', 'publisher', 'isbn', 'oclc', 'lccn', 'contribtor', 'subject', 'place', 'person', 'time']
        q_list += ['%s:(%s)' % (k, param[k]) for k in check_params if k in param]
    return (q_list, use_dismax)

def run_solr_query(param = {}, rows=100, page=1, sort=None, spellcheck_count=None):
    # called by do_search
    if spellcheck_count == None:
        spellcheck_count = default_spellcheck_count
    offset = rows * (page - 1)

    (q_list, use_dismax) = build_q_list(param)

    fields = ['key', 'author_name', 'author_key', 'title', 'subtitle', 'edition_count', 'ia', 'has_fulltext', 'first_publish_year', 'cover_edition_key', 'public_scan_b', 'lending_edition_s', 'overdrive_s', 'ia_collection_s']
    fl = ','.join(fields)
    if use_dismax:
        q = web.urlquote(' '.join(q_list))
        solr_select = solr_select_url + "?defType=dismax&q.op=AND&q=%s&qf=text+title^5+author_name^5&bf=sqrt(edition_count)^10&start=%d&rows=%d&fl=%s&wt=standard" % (q, offset, rows, fl)
    else:
        q = web.urlquote(' '.join(q_list + ['_val_:"sqrt(edition_count)"^10']))
        solr_select = solr_select_url + "?q.op=AND&q=%s&start=%d&rows=%d&fl=%s&wt=standard" % (q, offset, rows, fl)
    solr_select += '&spellcheck=true&spellcheck.count=%d' % spellcheck_count
    solr_select += "&facet=true&" + '&'.join("facet.field=" + f for f in facet_fields)

    if 'public_scan' in param:
        v = param.pop('public_scan').lower()
        if v in ('true', 'false'):
            if v == 'false':
                # also constrain on print disabled since the index may not be in sync
                param.setdefault('print_disabled', 'false')
            solr_select += '&fq=public_scan_b:%s' % v

    if 'print_disabled' in param:
        v = param.pop('print_disabled').lower()
        if v in ('true', 'false'):
            solr_select += '&fq=%ssubject_key:protected_daisy' % ('-' if v == 'false' else '')

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

    stats.begin("solr", url=solr_select)
    reply = urllib.urlopen(solr_select).read()
    stats.end()
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
            is_advanced = bool(param.get('q')),
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
            if a in spell_map or a in ('sqrt', 'edition_count'):
                continue
            spell_map[a] = [i.text for i in e.find("arr[@name='suggestion']")]

    docs = root.find('result')
    return web.storage(
        facet_counts = read_facets(root),
        docs = docs,
        is_advanced = bool(param.get('q')),
        num_found = (int(docs.attrib['numFound']) if docs is not None else None),
        solr_select = solr_select,
        q_list = q_list,
        error = None,
        spellcheck = spell_map,
    )

def get_doc(doc): # called from work_search template
    e_ia = doc.find("arr[@name='ia']")
    first_pub = None
    e_first_pub = doc.find("int[@name='first_publish_year']")
    if e_first_pub is not None:
        first_pub = e_first_pub.text
    e_first_edition = doc.find("str[@name='first_edition']")
    first_edition = None
    if e_first_edition is not None:
        first_edition = e_first_edition.text

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
        authors = [web.storage(key=key, name=name, url="/authors/%s/%s" % (key, (urlsafe(name) if name is not None else 'noname'))) for key, name in zip(ak, an)]

    cover = doc.find("str[@name='cover_edition_key']")
    e_public_scan = doc.find("bool[@name='public_scan_b']")
    e_overdrive = doc.find("str[@name='overdrive_s']")
    e_lending_edition = doc.find("str[@name='lending_edition_s']")
    e_collection = doc.find("str[@name='ia_collection_s']")
    collections = set()
    if e_collection is not None:
        collections = set(e_collection.text.split(';'))

    doc = web.storage(
        key = doc.find("str[@name='key']").text,
        title = doc.find("str[@name='title']").text,
        edition_count = int(doc.find("int[@name='edition_count']").text),
        ia = [e.text for e in (e_ia if e_ia is not None else [])],
        has_fulltext = (doc.find("bool[@name='has_fulltext']").text == 'true'),
        public_scan = ((e_public_scan.text == 'true') if e_public_scan is not None else (e_ia is not None)),
        overdrive = (e_overdrive.text.split(';') if e_overdrive is not None else []),
        lending_edition = (e_lending_edition.text if e_lending_edition is not None else None),
        collections = collections,
        authors = authors,
        first_publish_year = first_pub,
        first_edition = first_edition,
        subtitle = work_subtitle,
        cover_edition_key = (cover.text if cover is not None else None),
    )
    doc.url = '/works/' + doc.key + '/' + urlsafe(doc.title)
    return doc

re_subject_types = re.compile('^(places|times|people)/(.*)')
subject_types = {
    'places': 'place',
    'times': 'time',
    'people': 'person',
    'subjects': 'subject',
}

re_year_range = re.compile('^(\d{4})-(\d{4})$')

def work_object(w): # called by works_by_author
    ia = w.get('ia', [])
    obj = dict(
        authors = [web.storage(key='/authors/' + k, name=n) for k, n in zip(w['author_key'], w['author_name'])],
        edition_count = w['edition_count'],
        key = '/works/' + w['key'],
        title = w['title'],
        public_scan = w.get('public_scan_b', bool(ia)),
        lending_edition = w.get('lending_edition_s', ''),
        overdrive = (w['overdrive_s'].split(';') if 'overdrive_s' in w else []),
        collections = set(w['ia_collection_s'].split(';') if 'ia_collection_s' in w else []),
        url = '/works/' + w['key'] + '/' + urlsafe(w['title']),
        cover_edition_key = w.get('cover_edition_key'),
        first_publish_year = (w['first_publish_year'] if 'first_publish_year' in w else None),
        ia = w.get('ia', [])
    )
    for f in 'has_fulltext', 'subtitle':
        if w.get(f):
            obj[f] = w[f]
    return web.storage(obj)

def get_facet(facets, f, limit=None):
    return list(web.group(facets[f][:limit * 2] if limit else facets[f], 2))

SUBJECTS = [
    web.storage(name="subject", key="subjects", prefix="/subjects/", facet="subject_facet", facet_key="subject_key"),
    web.storage(name="person", key="people", prefix="/subjects/person:", facet="person_facet", facet_key="person_key"),
    web.storage(name="place", key="places", prefix="/subjects/place:", facet="place_facet", facet_key="place_key"),
    web.storage(name="time", key="times", prefix="/subjects/time:", facet="time_facet", facet_key="time_key"),
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

re_chars = re.compile("([%s])" % re.escape(r'+-!(){}[]^"~*?:\\'))
re_year = re.compile(r'\b(\d+)$')

def find_ebook_count(field, key):
    q = '%s_key:%s+AND+(overdrive_s:*+OR+ia:*)' % (field, re_chars.sub(r'\\\1', key).encode('utf-8'))

    root_url = solr_select_url + '?wt=json&indent=on&rows=%d&start=%d&q.op=AND&q=%s&fl=edition_key'
    rows = 1000

    ebook_count = 0
    start = 0
    solr_url = root_url % (rows, start, q)

    stats.begin("solr", url=solr_url)
    response = json.load(urllib.urlopen(solr_url))['response']
    stats.end()

    num_found = response['numFound']
    print 'num_found:', num_found
    years = defaultdict(int)
    while start < num_found:
        if start:
            solr_url = root_url % (rows, start, q)
            print solr_url
            stats.begin("solr", url=solr_url)
            response = json.load(urllib.urlopen(solr_url))['response']
            stats.end()
        for doc in response['docs']:
            for k in doc['edition_key']:
                e = web.ctx.site.get('/books/' + k)
                ia = set(i[3:] for i in e.get('source_records', []) if i.startswith('ia:'))
                if e.get('ocaid'):
                    ia.add(e['ocaid'])
                pub_date = e.get('publish_date')
                pub_year = -1
                if pub_date:
                    m = re_year.search(pub_date)
                    if m:
                        pub_year = int(m.group(1))
                ebook_count = len(ia)
                if 'overdrive' in e.get('identifiers', {}):
                    ebook_count += len(e['identifiers']['overdrive'])
                if ebook_count:
                    years[pub_year] += ebook_count
        start += rows

    return dict(years)

def get_ebook_count(field, key, publish_year=None):
    def db_lookup(field, key, publish_year=None):
        sql = 'select sum(ebook_count) as num from subjects where field=$field and key=$key'
        if publish_year:
            if isinstance(publish_year, list):
                sql += ' and publish_year between $y1 and $y2'
                (y1, y2) = publish_year
            else:
                sql += ' and publish_year=$publish_year'
        return list(ebook_count_db.query(sql, vars=locals()))[0].num

    total = db_lookup(field, key, publish_year)
    if total:
        return total
    elif publish_year:
        sql = 'select ebook_count as num from subjects where field=$field and key=$key limit 1'
        if len(list(ebook_count_db.query(sql, vars=locals()))) != 0:
            return 0
    years = find_ebook_count(field, key)
    if not years:
        return 0
    for year, count in sorted(years.iteritems()):
        ebook_count_db.query('insert into subjects (field, key, publish_year, ebook_count) values ($field, $key, $year, $count)', vars=locals())

    return db_lookup(field, key, publish_year)

def get_subject(key, details=False, offset=0, sort='editions', limit=12, **filters):
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
    sort_options = {
        'editions': 'edition_count desc',
        'new': 'first_publish_year desc',
    }
    sort_order = sort_options.get(sort) or sort_options['editions']

    return SubjectEngine().get_subject(key, details=details, offset=offset, sort=sort_order, limit=limit, **filters)
        
class SubjectEngine:        
    def get_subject(self, key, details=False, offset=0, limit=12, sort='first_publish_year desc', **filters):
        meta = self.get_meta(key)

        q = self.make_query(key, filters)    
        subject_type = meta.name
        name = meta.path.replace("_", " ")
        
        if details:
            kw = self.query_optons_for_details()
        else:
            kw = {}
            
        from search import work_search
        result = work_search(q, offset=offset, limit=limit, sort=sort, **kw)
        for w in result.docs:
            w.ia = w.ia and w.ia[0] or None

        subject = Subject(
            key=key,
            name=name,
            subject_type=subject_type,
            work_count = result['num_found'],
            works=result['docs']
        )
        
        if details:
            #subject.ebook_count = dict(result.facets["has_fulltext"]).get("true", 0)
            subject.ebook_count = self.get_ebook_count(meta.name, q[meta.facet_key], q.get('publish_year'))

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
        
    def get_meta(self, key):
        prefix = self.parse_key(key)[0]
        meta = finddict(SUBJECTS, prefix=prefix)

        meta = web.storage(meta)
        meta.path = web.lstrips(key, meta.prefix)
        return meta

    def parse_key(self, key):
        """Returns prefix and path from the key.
        """
        m = web.re_compile(r'/subjects/(place:|time:|person:|)(.+)').match(key)
        if m:
            prefix = "/subjects/" + m.group(1)
            path = m.group(2)
            return prefix, path
        else:
            return None, None

    def make_query(self, key, filters):
        meta = self.get_meta(key)

        q = {meta.facet_key: str_to_key(meta.path).lower()}

        if filters:
            if filters.get("has_fulltext") == "true":
                q['has_fulltext'] = "true"
            if filters.get("publish_year"):
                q['publish_year'] = filters['publish_year']

        return q

    def get_ebook_count(self, name, value, publish_year):
        return get_ebook_count(name, value, publish_year)
    
    def facet_wrapper(self, facet, value, count):
        if facet == "publish_year":
            return [int(value), count]
        elif facet == "publisher_facet":
            return web.storage(name=value, count=count)
        elif facet == "author_facet":
            author = read_author_facet(value)
            return web.storage(name=author[1], key="/authors/" + author[0], count=count)
        elif facet in ["subject_facet", "person_facet", "place_facet", "time_facet"]:
            return web.storage(key=finddict(SUBJECTS, facet=facet).prefix + str_to_key(value).replace(" ", "_"), name=value, count=count)
        elif facet == "has_fulltext":
            return [value, count]
        else:
            return web.storage(name=value, count=count)
            
    def query_optons_for_details(self):
        """Additional query options to be added when details=True.
        """
        kw = {}
        kw['facets'] = [
            {"name": "author_facet", "sort": "count"},
            "language",
            "publisher_facet",
            {"name": "publish_year", "limit": -1},
            "subject_facet", "person_facet", "place_facet", "time_facet",
            "has_fulltext"]
        kw['facet.mincount'] = 1
        kw['facet.limit'] = 25
        kw['facet_wrapper'] = self.facet_wrapper
        return kw
    
class subjects_json(delegate.page):
    path = '(/subjects/[^/]+)'
    encoding = "json"

    @jsonapi
    def GET(self, key):
        if key.lower() != key:
            raise web.redirect(key.lower())

        i = web.input(offset=0, limit=12, details='false', has_fulltext='false', sort='editions')

        filters = {}
        if i.get('has_fulltext') == 'true':
            filters['has_fulltext'] = 'true'

        if i.get('published_in'):
            if '-' in i.published_in:
                begin, end = i.published_in.split('-', 1)

                if safeint(begin, None) is not None and safeint(end, None) is not None:
                    filters['publish_year'] = [begin, end]
            else:
                y = safeint(i.published_in, None)
                if y is not None:
                    filters['publish_year'] = i.published_in

        i.limit = safeint(i.limit, 12)
        i.offset = safeint(i.offset, 0)

        subject = get_subject(key, offset=i.offset, limit=i.limit, sort=i.sort, details=i.details.lower() == 'true', **filters)
        return json.dumps(subject)

class subject_works_json(delegate.page):
    path = '(/subjects/[^/]+)/works'
    encoding = "json"

    @jsonapi
    def GET(self, key):
        if key.lower() != key:
            raise web.redirect(key.lower())

        i = web.input(offset=0, limit=12, has_fulltext="false")

        filters = {}
        if i.get("has_fulltext") == "true":
            filters["has_fulltext"] = "true"

        if i.get("published_in"):
            if "-" in i.published_in:
                begin, end = i.published_in.split("-", 1)

                if safeint(begin, None) is not None and safeint(end, None) is not None:
                    filters["publish_year"] = (begin, end)
            else:
                y = safeint(i.published_in, None)
                if y is not None:
                    filters["publish_year"] = i.published_in

        i.limit = safeint(i.limit, 12)
        i.offset = safeint(i.offset, 0)

        subject = get_subject(key, offset=i.offset, limit=i.limit, details=False, **filters)
        return json.dumps(subject)


class subjects(delegate.page):
    path = '(/subjects/[^/]+)'

    def GET(self, key):
        if key.lower() != key:
            raise web.redirect(key.lower())

        # temporary code to handle url change from /people/ to /person:
        if key.count("/") == 3:
            key2 = key
            key2 = key2.replace("/people/", "/person:")
            key2 = key2.replace("/places/", "/place:")
            key2 = key2.replace("/times/", "/time:")
            if key2 != key:
                raise web.seeother(key2)

        page = get_subject(key, details=True)

        if page.work_count == 0:
            return render_template('subjects/notfound.tmpl', key)

        return render_template("subjects", page)

re_olid = re.compile('^OL\d+([AMW])$')
olid_urls = {'A': 'authors', 'M': 'editions', 'W': 'works'}

class search(delegate.page):
    def redirect_if_needed(self, i):
        params = {}
        need_redirect = False
        for k, v in i.items():
            if k in plurals:
                params[k] = None
                k = plurals[k]
                need_redirect = True
            if isinstance(v, list):
                if v == []:
                    continue
                clean = [normalize('NFC', b.strip()) for b in v]
                if clean != v:
                    need_redirect = True
                if len(clean) == 1 and clean[0] == u'':
                    clean = None
            else:
                clean = normalize('NFC', v.strip())
                if clean == '':
                    need_redirect = True
                    clean = None
                if clean != v:
                    need_redirect = True
            params[k] = clean
        if need_redirect:
            raise web.seeother(web.changequery(**params))

    def isbn_redirect(self, isbn_param):
        isbn = read_isbn(isbn_param)
        if not isbn:
            return
        editions = []
        for f in 'isbn_10', 'isbn_13':
            q = {'type': '/type/edition', f: isbn}
            editions += web.ctx.site.things(q)
        if len(editions) == 1:
            raise web.seeother(editions[0])

    def GET(self):
        global ftoken_db
        i = web.input(author_key=[], language=[], first_publish_year=[], publisher_facet=[], subject_facet=[], person_facet=[], place_facet=[], time_facet=[])
        if i.get('ftokens') and ',' not in i.ftokens:
            token = i.ftokens
            if ftoken_db is None:
                ftoken_db = dbm.open('/olsystem/ftokens', 'r')
            if ftoken_db.get(token):
                raise web.seeother('/subjects/' + ftoken_db[token].decode('utf-8').lower().replace(' ', '_'))

        if i.get('wisbn'):
            i.isbn = i.wisbn

        self.redirect_if_needed(i)

        if 'isbn' in i and all(not v for k, v in i.items() if k != 'isbn'):
            self.isbn_redirect(i.isbn)

        q_list = []
        q = i.get('q', '').strip()
        if q:
            m = re_olid.match(q)
            if m:
                raise web.seeother('/%s/%s' % (olid_urls[m.group(1)], q))
            m = re_isbn_field.match(q)
            if m:
                self.isbn_redirect(m.group(1))
            q_list.append(q)
        for k in ('title', 'author', 'isbn', 'subject', 'place', 'person', 'publisher'):
            if k in i:
                v = re_to_esc.sub(lambda m:'\\' + m.group(), i[k].strip())
                q_list.append(k + ':' + v)

        return render.work_search(i, ' '.join(q_list), do_search, get_doc)

def works_by_author(akey, sort='editions', page=1, rows=100):
    # called by merge_author_works
    q='author_key:' + akey
    offset = rows * (page - 1)
    fields = ['key', 'author_name', 'author_key', 'title', 'subtitle',
        'edition_count', 'ia', 'cover_edition_key', 'has_fulltext',
        'first_publish_year', 'public_scan_b', 'lending_edition_s',
        'overdrive_s', 'ia_collection_s']
    fl = ','.join(fields)
    solr_select = solr_select_url + "?q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=%s&wt=json" % (q, offset, rows, fl)
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
    stats.begin("solr", url=solr_select)
    reply = json.load(urllib.urlopen(solr_select))
    stats.end()
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
        stats.begin("solr", url=solr_select)
        json_data = urllib.urlopen(solr_select).read()
        stats.end()
    reply = json.loads(json_data)

    if reply['response']['numFound'] == 0:
        return []
    return reply["response"]['docs'][0].get('edition_key', [])

def simple_search(q, offset=0, rows=20, sort=None):
    solr_select = solr_select_url + "?version=2.2&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=*%%2Cscore&qt=standard&wt=json" % (web.urlquote(q), offset, rows)
    if sort:
        solr_select += "&sort=" + web.urlquote(sort)

    stats.begin("solr", url=solr_select)
    json_data = urllib.urlopen(solr_select)
    stats.end()
    return json.load(json_data)

def top_books_from_author(akey, rows=5, offset=0):
    q = 'author_key:(' + akey + ')'
    solr_select = solr_select_url + "?q=%s&start=%d&rows=%d&fl=key,title,edition_count&wt=json&sort=edition_count+desc" % (q, offset, rows)
    stats.begin("solr", url=solr_select)
    response = json.load(urllib.urlopen(solr_select))['response']
    stats.end()
    return {
        'books': [web.storage(doc) for doc in response['docs']],
        'total': response['numFound'],
    }

def do_merge():
    return

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
            q = escape_bracket(q)
            solr_select = solr_subject_select_url + "?q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=name,type,count&qt=standard&wt=json" % (web.urlquote(q), offset, limit)
            solr_select += '&sort=count+desc'
            stats.begin("solr", url=solr_select)
            json_data = urllib.urlopen(solr_select).read()
            stats.end()
            return json.loads(json_data)
        return render_template('search/subjects.tmpl', get_results)

class author_search(delegate.page):
    path = '/search/authors'
    def GET(self):
        def get_results(q, offset=0, limit=100):
            q = escape_bracket(q)
            solr_select = solr_author_select_url + "?q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=*&qt=standard&wt=json" % (web.urlquote(q), offset, limit)
            solr_select += '&sort=work_count+desc'
            stats.begin("solr", url=solr_select)
            json_data = urllib.urlopen(solr_select).read()
            stats.end()
            return json.loads(json_data)
        return render_template('search/authors.tmpl', get_results)

class edition_search(delegate.page):
    path = '/search/editions'
    def GET(self):
        def get_results(q, offset=0, limit=100):
            q = escape_bracket(q)
            solr_select = solr_edition_select_url + "?q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=*&qt=standard&wt=json" % (web.urlquote(q), offset, limit)
            stats.begin("solr", url=solr_select)
            json_data = urllib.urlopen(solr_select).read()
            stats.end()
            return json.loads(json_data)
        return render_template('search/editions.tmpl', get_results)

class search_json(delegate.page):
    path = "/search"
    encoding = "json"

    def GET(self):
        i = web.input()
        if 'query' in i:
            query = simplejson.loads(i.query)
        else:
            query = i

        limit = query.pop("limit", None)
        offset = safeint(query.pop("offset", 0))

        from openlibrary.utils.solr import Solr
        import simplejson

        solr = Solr("http://%s/solr/works" % solr_host)
        result = solr.select(query, rows=limit, start=offset)
        web.header('Content-Type', 'application/json')
        return delegate.RawText(simplejson.dumps(result, indent=True))
