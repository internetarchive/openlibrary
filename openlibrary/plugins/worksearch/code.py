import six
from six.moves.urllib.parse import urlencode

import web
import re
from lxml.etree import XML, XMLSyntaxError
from infogami.utils import delegate, stats
from infogami import config
from infogami.utils.view import render, render_template, safeint, public
import simplejson as json
from openlibrary.core.models import Edition  # noqa: E402
from openlibrary.core.lending import get_availability_of_ocaids, add_availability
from openlibrary.plugins.openlibrary.processors import urlsafe
from openlibrary.plugins.inside.code import fulltext_search
from openlibrary.utils import escape_bracket
from openlibrary.utils.isbn import normalize_isbn, opposite_isbn
from unicodedata import normalize
import logging

from six.moves import urllib

logger = logging.getLogger("openlibrary.worksearch")

if hasattr(config, 'plugin_worksearch'):
    solr_host = config.plugin_worksearch.get('solr', 'localhost')
    solr_select_url = "http://%s/solr/select" % solr_host

    default_spellcheck_count = config.plugin_worksearch.get('spellcheck_count', 10)


ALL_FIELDS = [
    "key",
    "redirects",
    "title",
    "subtitle",
    "alternative_title",
    "alternative_subtitle",
    "edition_key",
    "by_statement",
    "publish_date",
    "lccn",
    "ia",
    "oclc",
    "isbn",
    "contributor",
    "publish_place",
    "publisher",
    "first_sentence",
    "author_key",
    "author_name",
    "author_alternative_name",
    "subject",
    "person",
    "place",
    "time",
    "has_fulltext",
    "title_suggest",
    "edition_count",
    "publish_year",
    "language",
    "number_of_pages",
    "ia_count",
    "publisher_facet",
    "author_facet",
    "first_publish_year",
    "subject_key",
    "person_key",
    "place_key",
    "time_key",
]
FACET_FIELDS = [
    "has_fulltext",
    "author_facet",
    "language",
    "first_publish_year",
    "publisher_facet",
    "subject_facet",
    "person_facet",
    "place_facet",
    "time_facet",
    "public_scan_b",
]
FIELD_NAME_MAP = {
    'author': 'author_name',
    'authors': 'author_name',
    'by': 'author_name',
    'publishers': 'publisher',
}
OLID_URLS = {'A': 'authors', 'M': 'books', 'W': 'works'}

re_to_esc = re.compile(r'[\[\]:]')
re_isbn_field = re.compile(r'^\s*(?:isbn[:\s]*)?([-0-9X]{9,})\s*$', re.I)
re_author_key = re.compile(r'(OL\d+A)')
re_fields = re.compile(r'(-?%s):' % '|'.join(ALL_FIELDS + list(FIELD_NAME_MAP)), re.I)
re_op = re.compile(' +(OR|AND)$')
re_author_facet = re.compile(r'^(OL\d+A) (.*)$')
re_pre = re.compile(r'<pre>(.*)</pre>', re.S)
re_subject_types = re.compile('^(places|times|people)/(.*)')
re_olid = re.compile(r'^OL\d+([AMW])$')

plurals = dict((f + 's', f) for f in ('publisher', 'author'))


def read_author_facet(af):
    # example input: "OL26783A Leo Tolstoy"
    return re_author_facet.match(af).groups()


def get_language_name(code):
    lang = web.ctx.site.get('/languages/' + code)
    return lang.name if lang else "'%s' unknown" % code

def read_facets(root):
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


def parse_query_fields(q):
    found = [(m.start(), m.end()) for m in re_fields.finditer(q)]
    first = q[:found[0][0]].strip() if found else q.strip()
    if first:
        yield {'field': 'text', 'value': first.replace(':', r'\:')}
    for field_num in range(len(found)):
        op_found = None
        f = found[field_num]
        field_name = q[f[0]:f[1]-1].lower()
        if field_name in FIELD_NAME_MAP:
            field_name = FIELD_NAME_MAP[field_name]
        if field_num == len(found)-1:
            v = q[f[1]:].strip()
        else:
            v = q[f[1]:found[field_num+1][0]].strip()
            m = re_op.search(v)
            if m:
                v = v[:-len(m.group(0))]
                op_found = m.group(1)
        if field_name == 'isbn':
            isbn = normalize_isbn(v)
            if isbn:
                v = isbn
        yield {'field': field_name, 'value': v.replace(':', r'\:')}
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
            isbn = normalize_isbn(q_param)
            if isbn and len(isbn) in (10, 13):
                q_list.append('isbn:(%s)' % isbn)
            else:
                q_list.append(q_param.strip().replace(':', r'\:'))
                use_dismax = True
    else:
        if 'author' in param:
            v = param['author'].strip()
            m = re_author_key.search(v)
            if m:
                q_list.append("author_key:(%s)" % m.group(1))
            else:
                v = re_to_esc.sub(lambda m:'\\' + m.group(), v)
                # Somehow v can be empty at this point,
                #   passing the following with empty strings causes a severe error in SOLR
                if v:
                    q_list.append("(author_name:(%(name)s) OR author_alternative_name:(%(name)s))" % {'name': v})

        check_params = ['title', 'publisher', 'oclc', 'lccn', 'contribtor', 'subject', 'place', 'person', 'time']
        q_list += ['%s:(%s)' % (k, param[k]) for k in check_params if k in param]
        if param.get('isbn'):
            q_list.append('isbn:(%s)' % (normalize_isbn(param['isbn']) or param['isbn']))
    return (q_list, use_dismax)

def parse_json_from_solr_query(url):
    solr_result = execute_solr_query(url)
    return parse_json(solr_result)

def execute_solr_query(url):
    stats.begin("solr", url=url)
    try:
        solr_result = urllib.request.urlopen(url, timeout=3)
    except Exception as e:
        logger.exception("Failed solr query")
        return None
    finally:
        stats.end()
    return solr_result

def parse_json(raw_file):
    if raw_file is None:
        logger.error("Error parsing empty search engine response")
        return None
    try:
        json_result = json.load(raw_file)
    except json.JSONDecodeError as e:
        logger.exception("Error parsing search engine response")
        return None
    return json_result

def run_solr_query(param = {}, rows=100, page=1, sort=None, spellcheck_count=None, offset=None, fields=None):
    # called by do_search
    if spellcheck_count == None:
        spellcheck_count = default_spellcheck_count

    # use page when offset is not specified
    if offset is None:
        offset = rows * (page - 1)

    (q_list, use_dismax) = build_q_list(param)
    params = [
        ('fl', ','.join(fields or [
            'key', 'author_name', 'author_key', 'title', 'subtitle', 'edition_count',
            'ia', 'has_fulltext', 'first_publish_year', 'cover_i', 'cover_edition_key',
            'public_scan_b', 'lending_edition_s', 'lending_identifier_s',
            'ia_collection_s'])),
        ('fq', 'type:work'),
        ('q.op', 'AND'),
        ('start', offset),
        ('rows', rows),

        ('spellcheck', 'true'),
        ('spellcheck.count', spellcheck_count),
        ('facet', 'true'),
    ]

    for facet in FACET_FIELDS:
        params.append(('facet.field', facet))

    if q_list:
        if use_dismax:
            params.append(('q', ' '.join(q_list)))
            params.append(('defType', 'dismax'))
            params.append(('qf', 'text title^5 author_name^5'))
            params.append(('bf', 'sqrt(edition_count)^10'))
        else:
            params.append(('q', ' '.join(q_list + ['_val_:"sqrt(edition_count)"^10'])))

    if 'public_scan' in param:
        v = param.pop('public_scan').lower()
        if v in ('true', 'false'):
            if v == 'false':
                # also constrain on print disabled since the index may not be in sync
                param.setdefault('print_disabled', 'false')
            params.append(('fq', 'public_scan_b:%s' % v))

    if 'print_disabled' in param:
        v = param.pop('print_disabled').lower()
        if v in ('true', 'false'):
            minus = '-' if v == 'false' else ''
            params.append(('fq', '%ssubject_key:protected_daisy' % minus))

    if 'has_fulltext' in param:
        v = param['has_fulltext'].lower()
        if v not in ('true', 'false'):
            del param['has_fulltext']
        params.append(('fq', 'has_fulltext:%s' % v))

    for field in FACET_FIELDS:
        if field == 'has_fulltext':
            continue
        if field == 'author_facet':
            field = 'author_key'
        if field not in param:
            continue
        values = param[field]
        params += [('fq', '%s:"%s"' % (field, val)) for val in values if val]

    if sort:
        params.append(('sort', sort))

    params.append(('wt', param.get('wt', 'standard')))
    params = [(k, v.encode('utf-8') if isinstance(v, six.string_types) else v)
              for (k, v) in params]
    url = solr_select_url + '?' + urlencode(params)
    solr_result = execute_solr_query(url)
    if solr_result is None:
        return (None, url, q_list)
    reply = solr_result.read()
    return (reply, url, q_list)

def do_search(param, sort, page=1, rows=100, spellcheck_count=None):
    (reply, solr_select, q_list) = run_solr_query(
        param, rows, page, sort, spellcheck_count)
    is_bad = False
    if not reply or reply.startswith('<html'):
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
    e_lending_edition = doc.find("str[@name='lending_edition_s']")
    e_lending_identifier = doc.find("str[@name='lending_identifier_s']")
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
        lending_edition = (e_lending_edition.text if e_lending_edition is not None else None),
        lending_identifier=(
            e_lending_identifier.text if e_lending_identifier is not None else None),
        collections = collections,
        authors = authors,
        first_publish_year = first_pub,
        first_edition = first_edition,
        subtitle = work_subtitle,
        cover_edition_key = (cover.text if cover is not None else None),
    )

    doc.url = doc.key + '/' + urlsafe(doc.title)

    if not doc.public_scan and doc.lending_identifier:
        store_doc = web.ctx.site.store.get("ebooks/" + doc.lending_identifier) or {}
        doc.checked_out = store_doc.get("borrowed") == "true"
    elif not doc.public_scan and doc.lending_edition:
        store_doc = web.ctx.site.store.get("ebooks/books/" + doc.lending_edition) or {}
        doc.checked_out = store_doc.get("borrowed") == "true"
    else:
        doc.checked_out = "false"
    return doc

def work_object(w): # called by works_by_author
    ia = w.get('ia', [])
    obj = dict(
        authors = [web.storage(key='/authors/' + k, name=n) for k, n in zip(w['author_key'], w['author_name'])],
        edition_count = w['edition_count'],
        key = w['key'],
        title = w['title'],
        public_scan = w.get('public_scan_b', bool(ia)),
        lending_edition = w.get('lending_edition_s', ''),
        lending_identifier = w.get('lending_identifier_s', ''),
        collections = set(w['ia_collection_s'].split(';') if 'ia_collection_s' in w else []),
        url = w['key'] + '/' + urlsafe(w['title']),
        cover_edition_key = w.get('cover_edition_key'),
        first_publish_year = (w['first_publish_year'] if 'first_publish_year' in w else None),
        ia = w.get('ia', []),
        cover_i = w.get('cover_i')
    )

    if obj['lending_identifier']:
        doc = web.ctx.site.store.get("ebooks/" + obj['lending_identifier']) or {}
        obj['checked_out'] = doc.get("borrowed") == "true"
    else:
        obj['checked_out'] = False

    for f in 'has_fulltext', 'subtitle':
        if w.get(f):
            obj[f] = w[f]
    return web.storage(obj)

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
        isbn = normalize_isbn(isbn_param)
        if not isbn:
            return

        ed = Edition.from_isbn(isbn)
        if ed:
            web.seeother(ed.key)


    def GET(self):
        # Enable patrons to search for query q2 within collection q
        # q2 param gets removed and prepended to q via a redirect
        _i = web.input(q='', q2='')
        if _i.q.strip() and _i.q2.strip():
            _i.q = _i.q2.strip() + ' ' + _i.q.strip()
            _i.pop('q2')
            raise web.seeother('/search?' + urllib.parse.urlencode(_i))

        i = web.input(author_key=[], language=[], first_publish_year=[], publisher_facet=[], subject_facet=[], person_facet=[], place_facet=[], time_facet=[], public_scan_b=[])

        # Send to full-text Search Inside if checkbox checked
        if i.get('search-fulltext'):
            raise web.seeother('/search/inside?' + urllib.parse.urlencode({'q': i.get('q', '')}))

        if i.get('wisbn'):
            i.isbn = i.wisbn

        self.redirect_if_needed(i)

        if 'isbn' in i:
            self.isbn_redirect(i.isbn)

        q_list = []
        q = i.get('q', '').strip()
        if q:
            m = re_olid.match(q)
            if m:
                raise web.seeother('/%s/%s' % (OLID_URLS[m.group(1)], q))
            m = re_isbn_field.match(q)
            if m:
                self.isbn_redirect(m.group(1))
            q_list.append(q)
        for k in ('title', 'author', 'isbn', 'subject', 'place', 'person', 'publisher'):
            if k in i:
                v = re_to_esc.sub(lambda m:'\\' + m.group(), i[k].strip())
                q_list.append(k + ':' + v)
        page = render.work_search(
            i, ' '.join(q_list), do_search, get_doc,
            get_availability_of_ocaids, fulltext_search,
            FACET_FIELDS)
        page.v2 = True
        return page


def works_by_author(akey, sort='editions', page=1, rows=100, has_fulltext=False):
    # called by merge_author_works
    q='author_key:' + akey
    offset = rows * (page - 1)
    fields = ['key', 'author_name', 'author_key', 'title', 'subtitle',
        'edition_count', 'ia', 'cover_edition_key', 'has_fulltext',
        'first_publish_year', 'public_scan_b', 'lending_edition_s', 'lending_identifier_s',
        'ia_collection_s', 'cover_i']
    fl = ','.join(fields)
    fq = 'has_fulltext:true' if has_fulltext else ''  # ebooks_only
    solr_select = solr_select_url + "?fq=type:work&q.op=AND&q=%s&fq=%s&start=%d&rows=%d&fl=%s&wt=json" % (q, fq, offset, rows, fl)
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
    reply = parse_json_from_solr_query(solr_select)
    if reply is None:
        return web.storage(
            num_found = 0,
            works = [],
            years = [],
            get_facet = [],
            sort = sort,
        )
    # TODO: Deep JSON structure defense - for now, let it blow up so easier to detect
    facets = reply['facet_counts']['facet_fields']
    works = [work_object(w) for w in reply['response']['docs']]

    def get_facet(f, limit=None):
        return list(web.group(facets[f][:limit * 2] if limit else facets[f], 2))

    return web.storage(
        num_found = int(reply['response']['numFound']),
        works = add_availability(works),
        years = [(int(k), v) for k, v in get_facet('publish_year')],
        get_facet = get_facet,
        sort = sort,
    )

def sorted_work_editions(wkey, json_data=None):
    """Setting json_data to a real value simulates getting SOLR data back, i.e. for testing (but ick!)"""
    q = 'key:' + wkey
    if json_data:
        reply = json.loads(json_data)
    else:
        solr_select = solr_select_url + "?version=2.2&q.op=AND&q=%s&rows=10&fl=edition_key&qt=standard&wt=json" % q
        reply = parse_json_from_solr_query(solr_select)
    if reply is None or reply.get('response', {}).get('numFound', 0) == 0:
        return []
    # TODO: Deep JSON structure defense - for now, let it blow up so easier to detect
    return reply["response"]['docs'][0].get('edition_key', [])


def top_books_from_author(akey, rows=5, offset=0):
    q = 'author_key:(' + akey + ')'
    solr_select = solr_select_url + "?q=%s&start=%d&rows=%d&fl=key,title,edition_count,first_publish_year&wt=json&sort=edition_count+desc" % (q, offset, rows)
    json_result = parse_json_from_solr_query(solr_select)
    if json_result is None:
        return {'books': [], 'total': 0}
    # TODO: Deep JSON structure defense - for now, let it blow up so easier to detect
    response = json_result['response']
    return {
        'books': [web.storage(doc) for doc in response['docs']],
        'total': response['numFound'],
    }


class advancedsearch(delegate.page):
    path = "/advancedsearch"

    def GET(self):
        template = render_template("search/advancedsearch.html")
        template.v2 = True
        return template


def escape_colon(q, vf):
    if ':' not in q:
        return q
    parts = q.split(':')
    result = parts.pop(0)
    while parts:
        if not any(result.endswith(f) for f in vf):
            result += '\\'
        result += ':' + parts.pop(0)
    return result

def run_solr_search(solr_select):
    solr_result = execute_solr_query(solr_select)
    json_data = solr_result.read() if solr_result is not None else None
    return parse_search_response(json_data)

def parse_search_response(json_data):
    """Construct response for any input"""
    if json_data is None:
        return {'error': 'Error parsing empty search engine response'}
    try:
        return json.loads(json_data)
    except json.JSONDecodeError:
        logger.exception("Error parsing search engine response")
        m = re_pre.search(json_data)
        if m is None:
            return {'error': 'Error parsing search engine response'}
        error = web.htmlunquote(m.group(1))
        solr_error = 'org.apache.lucene.queryParser.ParseException: '
        if error.startswith(solr_error):
            error = error[len(solr_error):]
        return {'error': error}

class list_search(delegate.page):
    path = '/search/lists'

    def GET(self):
        i = web.input(q='', offset='0', limit='10')

        lists = self.get_results(i.q, i.offset, i.limit)

        return render_template('search/lists.tmpl', q=i.q, lists=lists)

    def get_results(self, q, offset=0, limit=100):
        if 'env' not in web.ctx:
            delegate.fakeload()

        keys = web.ctx.site.things({
            "type": "/type/list",
            "name~": q,
            "limit": int(limit),
            "offset": int(offset)
        })

        return web.ctx.site.get_many(keys)

class list_search_json(list_search):
    path = '/search/lists'
    encoding = 'json'

    def GET(self):
        i = web.input(q='', offset=0, limit=10)
        offset = safeint(i.offset, 0)
        limit = safeint(i.limit, 10)
        limit = min(100, limit)

        docs = self.get_results(i.q, offset=offset, limit=limit)

        response = {
            'start': offset,
            'docs': [doc.preview() for doc in docs]
        }

        web.header('Content-Type', 'application/json')
        return delegate.RawText(json.dumps(response))

class subject_search(delegate.page):
    path = '/search/subjects'
    def GET(self):
        return render_template('search/subjects.tmpl', self.get_results)

    def get_results(self, q, offset=0, limit=100):
        valid_fields = ['key', 'name', 'subject_type', 'work_count']
        q = escape_colon(escape_bracket(q), valid_fields)
        params = {
            "fq": "type:subject",
            "q.op": "AND",
            "q": q,
            "start": offset,
            "rows": limit,
            "fl": ",".join(valid_fields),
            "qt": "standard",
            "wt": "json",
            "sort": "work_count desc"
        }

        solr_select = solr_select_url + "?" + urllib.parse.urlencode(params, 'utf-8')
        results = run_solr_search(solr_select)
        response = results['response']

        for doc in response['docs']:
            doc['type'] = doc.get('subject_type', 'subject')
            doc['count'] = doc.get('work_count', 0)

        return results

class subject_search_json(subject_search):
    path = '/search/subjects'
    encoding = 'json'

    def GET(self):
        i = web.input(q='', offset=0, limit=100)
        offset = safeint(i.offset, 0)
        limit = safeint(i.limit, 100)
        limit = min(1000, limit)  # limit limit to 1000.

        response = self.get_results(i.q, offset=offset, limit=limit)['response']
        web.header('Content-Type', 'application/json')
        return delegate.RawText(json.dumps(response))

class author_search(delegate.page):
    path = '/search/authors'
    def GET(self):
        return render_template('search/authors.tmpl', self.get_results)

    def get_results(self, q, offset=0, limit=100):
        valid_fields = ['key', 'name', 'alternate_names', 'birth_date', 'death_date', 'date', 'work_count']
        q = escape_colon(escape_bracket(q), valid_fields)

        solr_select = solr_select_url + "?fq=type:author&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=*&qt=standard&wt=json" % (web.urlquote(q), offset, limit)
        solr_select += '&sort=work_count+desc'
        d = run_solr_search(solr_select)

        docs = d.get('response', {}).get('docs', [])
        for doc in docs:
            # replace /authors/OL1A with OL1A
            # The template still expects the key to be in the old format
            doc['key'] = doc['key'].split("/")[-1]
        return d

class author_search_json(author_search):
    path = '/search/authors'
    encoding = 'json'

    def GET(self):
        i = web.input(q='', offset=0, limit=100)
        offset = safeint(i.offset, 0)
        limit = safeint(i.limit, 100)
        limit = min(1000, limit) # limit limit to 1000.

        response = self.get_results(i.q, offset=offset, limit=limit)['response']
        web.header('Content-Type', 'application/json')
        return delegate.RawText(json.dumps(response))


@public
def work_search(query, sort=None, page=1, offset=0, limit=100):
    """
    params:
    query: dict
    sort: str editions|old|new|scans
    """
    sorts = {
        'editions': 'edition_count desc',
        'old': 'first_publish_year asc',
        'new': 'first_publish_year desc',
        'scans': 'ia_count desc'
    }
    query['wt'] = 'json'

    try:
        (reply, solr_select, q_list) = run_solr_query(query,
                                                      rows=limit,
                                                      page=page,
                                                      sort=sorts.get(sort),
                                                      offset=offset,
                                                      fields="*")
        response = json.loads(reply)['response'] or ''
    except (ValueError, IOError) as e:
        logger.error("Error in processing search API.")
        response = dict(start=0, numFound=0, docs=[], error=str(e))

    # backward compatibility
    response['num_found'] = response['numFound']
    response['docs'] = add_availability(response['docs'])
    return response


class search_json(delegate.page):
    path = "/search"
    encoding = "json"

    def GET(self):
        i = web.input()
        if 'query' in i:
            query = json.loads(i.query)
        else:
            query = i

        sort = query.get('sort', None)

        limit = safeint(query.pop("limit", "100"), default=100)
        if "offset" in query:
            offset = safeint(query.pop("offset", 0), default=0)
            page = None
        else:
            offset = None
            page = safeint(query.pop("page", "1"), default=1)

        response = work_search(query, sort=sort, page=page, offset=offset, limit=limit)

        web.header('Content-Type', 'application/json')
        return delegate.RawText(json.dumps(response, indent=True))

def setup():
    from openlibrary.plugins.worksearch import subjects

    # subjects module needs read_author_facet and solr_select_url.
    # Importing this module to access them will result in circular import.
    # Setting them like this to avoid circular-import.
    subjects.read_author_facet = read_author_facet
    if hasattr(config, 'plugin_worksearch'):
        subjects.solr_select_url = solr_select_url

    subjects.setup()

    from openlibrary.plugins.worksearch import languages, publishers
    publishers.setup()
    languages.setup()

setup()
