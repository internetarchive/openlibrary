from datetime import datetime
import copy
import json
import logging
import random
import re
import string
from typing import List, Tuple, Any, Union, Optional, Iterable, Dict
from unicodedata import normalize
from json import JSONDecodeError
import requests
import web
from lxml.etree import XML, XMLSyntaxError
from requests import Response
from six.moves import urllib

from infogami import config
from infogami.utils import delegate, stats
from infogami.utils.view import public, render, render_template, safeint
from openlibrary.core import cache
from openlibrary.core.lending import add_availability, get_availability_of_ocaids
from openlibrary.core.models import Edition  # noqa: E402
from openlibrary.plugins.inside.code import fulltext_search
from openlibrary.plugins.openlibrary.processors import urlsafe
from openlibrary.plugins.upstream.utils import urlencode
from openlibrary.utils import escape_bracket
from openlibrary.utils.ddc import (
    normalize_ddc,
    normalize_ddc_prefix,
    normalize_ddc_range,
)
from openlibrary.utils.isbn import normalize_isbn
from openlibrary.utils.lcc import (
    normalize_lcc_prefix,
    normalize_lcc_range,
    short_lcc_to_sortable_lcc,
)

logger = logging.getLogger("openlibrary.worksearch")

if hasattr(config, 'plugin_worksearch'):
    solr_select_url = (
        config.plugin_worksearch.get('solr_base_url', 'localhost') + '/select'
    )

    default_spellcheck_count = config.plugin_worksearch.get('spellcheck_count', 10)


ALL_FIELDS = [
    "key",
    "redirects",
    "title",
    "subtitle",
    "alternative_title",
    "alternative_subtitle",
    "edition_count",
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
    # Subjects
    "subject_key",
    "person_key",
    "place_key",
    "time_key",
    # Classifications
    "lcc",
    "ddc",
    "lcc_sort",
    "ddc_sort",
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
    'editions': 'edition_count',
    'by': 'author_name',
    'publishers': 'publisher',
    # "Private" fields
    # This is private because we'll change it to a multi-valued field instead of a
    # plain string at the next opportunity, which will make it much more usable.
    '_ia_collection': 'ia_collection_s',
}
SORTS = {
    'editions': 'edition_count desc',
    'old': 'def(first_publish_year, 9999) asc',
    'new': 'first_publish_year desc',
    'scans': 'ia_count desc',
    # Classifications
    'lcc_sort': 'lcc_sort asc',
    'lcc_sort asc': 'lcc_sort asc',
    'lcc_sort desc': 'lcc_sort desc',
    'ddc_sort': 'ddc_sort asc',
    'ddc_sort asc': 'ddc_sort asc',
    'ddc_sort desc': 'ddc_sort desc',
    # Random
    'random': 'random_1 asc',
    'random asc': 'random_1 asc',
    'random desc': 'random_1 desc',
    'random.hourly': lambda: f'random_{datetime.now():%Y%m%dT%H} asc',
    'random.daily': lambda: f'random_{datetime.now():%Y%m%d} asc',
}
DEFAULT_SEARCH_FIELDS = {
    'key',
    'author_name',
    'author_key',
    'title',
    'subtitle',
    'edition_count',
    'ia',
    'has_fulltext',
    'first_publish_year',
    'cover_i',
    'cover_edition_key',
    'public_scan_b',
    'lending_edition_s',
    'lending_identifier_s',
    'language',
    'ia_collection_s',
    # FIXME: These should be fetched from book_providers, but can't cause circular dep
    'id_project_gutenberg',
    'id_librivox',
    'id_standard_ebooks',
    'id_openstax',
}
OLID_URLS = {'A': 'authors', 'M': 'books', 'W': 'works'}

re_to_esc = re.compile(r'[\[\]:/]')
re_isbn_field = re.compile(r'^\s*(?:isbn[:\s]*)?([-0-9X]{9,})\s*$', re.I)
re_author_key = re.compile(r'(OL\d+A)')
re_fields = re.compile(r'(-?%s):' % '|'.join(ALL_FIELDS + list(FIELD_NAME_MAP)), re.I)
re_op = re.compile(' +(OR|AND)$')
re_range = re.compile(r'\[(?P<start>.*) TO (?P<end>.*)\]')
re_author_facet = re.compile(r'^(OL\d+A) (.*)$')
re_pre = re.compile(r'<pre>(.*)</pre>', re.S)
re_subject_types = re.compile('^(places|times|people)/(.*)')
re_olid = re.compile(r'^OL\d+([AMW])$')

plurals = {f + 's': f for f in ('publisher', 'author')}


@public
def get_solr_works(work_key: Iterable[str]) -> dict[str, dict]:
    from openlibrary.plugins.worksearch.search import get_solr

    return {
        doc['key']: doc
        for doc in get_solr().get_many(set(work_key), fields=DEFAULT_SEARCH_FIELDS)
    }


def process_sort(raw_sort):
    """
    :param str raw_sort:
    :rtype: str

    >>> process_sort('editions')
    'edition_count desc'
    >>> process_sort('editions, new')
    'edition_count desc,first_publish_year desc'
    >>> process_sort('random')
    'random_1 asc'
    >>> process_sort('random_custom_seed')
    'random_custom_seed asc'
    >>> process_sort('random_custom_seed desc')
    'random_custom_seed desc'
    >>> process_sort('random_custom_seed asc')
    'random_custom_seed asc'
    """

    def process_individual_sort(sort):
        if sort.startswith('random_'):
            return sort if ' ' in sort else sort + ' asc'
        else:
            solr_sort = SORTS[sort]
            return solr_sort() if callable(solr_sort) else solr_sort

    return ','.join(process_individual_sort(s.strip()) for s in raw_sort.split(','))


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
        if name == 'has_fulltext':  # boolean facets
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


def lcc_transform(raw):
    """
    Transform the lcc search field value
    :param str raw:
    :rtype: str
    """
    # e.g. lcc:[NC1 TO NC1000] to lcc:[NC-0001.00000000 TO NC-1000.00000000]
    # for proper range search
    m = re_range.match(raw)
    if m:
        lcc_range = [m.group('start').strip(), m.group('end').strip()]
        normed = normalize_lcc_range(*lcc_range)
        return f'[{normed[0] or lcc_range[0]} TO {normed[1] or lcc_range[1]}]'
    elif '*' in raw and not raw.startswith('*'):
        # Marshals human repr into solr repr
        # lcc:A720* should become A--0720*
        parts = raw.split('*', 1)
        lcc_prefix = normalize_lcc_prefix(parts[0])
        return (lcc_prefix or parts[0]) + '*' + parts[1]
    else:
        normed = short_lcc_to_sortable_lcc(raw.strip('"'))
        if normed:
            use_quotes = ' ' in normed or raw.startswith('"')
            return ('"%s"' if use_quotes else '%s*') % normed

    # If none of the transforms took
    return raw


def ddc_transform(raw):
    """
    Transform the ddc search field value
    :param str raw:
    :rtype: str
    """
    m = re_range.match(raw)
    if m:
        raw = [m.group('start').strip(), m.group('end').strip()]
        normed = normalize_ddc_range(*raw)
        return f'[{normed[0] or raw[0]} TO {normed[1] or raw[1]}]'
    elif raw.endswith('*'):
        return normalize_ddc_prefix(raw[:-1]) + '*'
    else:
        normed = normalize_ddc(raw.strip('"'))
        if normed:
            return normed[0]

    # if none of the transforms took
    return raw


def ia_collection_s_transform(raw):
    """
    Because this field is not a multi-valued field in solr, but a simple ;-separate
    string, we have to do searches like this for now.
    """
    result = raw
    if not result.startswith('*'):
        result = '*' + result
    if not result.endswith('*'):
        result += '*'
    return result


def parse_query_fields(q):
    found = [(m.start(), m.end()) for m in re_fields.finditer(q)]
    first = q[: found[0][0]].strip() if found else q.strip()
    if first:
        yield {'field': 'text', 'value': first.replace(':', r'\:')}
    for field_num in range(len(found)):
        op_found = None
        f = found[field_num]
        field_name = q[f[0] : f[1] - 1].lower()
        if field_name in FIELD_NAME_MAP:
            field_name = FIELD_NAME_MAP[field_name]
        if field_num == len(found) - 1:
            v = q[f[1] :].strip()
        else:
            v = q[f[1] : found[field_num + 1][0]].strip()
            m = re_op.search(v)
            if m:
                v = v[: -len(m.group(0))]
                op_found = m.group(1)
        if field_name == 'isbn':
            isbn = normalize_isbn(v)
            if isbn:
                v = isbn
        if field_name in ('lcc', 'lcc_sort'):
            v = lcc_transform(v)
        if field_name == ('ddc', 'ddc_sort'):
            v = ddc_transform(v)
        if field_name == 'ia_collection_s':
            v = ia_collection_s_transform(v)

        yield {'field': field_name, 'value': v.replace(':', r'\:')}
        if op_found:
            yield {'op': op_found}


def build_q_list(param):
    q_list = []
    if 'q' in param:
        # Solr 4+ has support for regexes (eg `key:/foo.*/`)! But for now, let's not
        # expose that and escape all '/'. Otherwise `key:/works/OL1W` is interpreted as
        # a regex.
        q_param = param['q'].strip().replace('/', '\\/')
    else:
        q_param = None
    use_dismax = False
    if q_param:
        if q_param == '*:*':
            q_list.append(q_param)
        elif 'NOT ' in q_param:  # this is a hack
            q_list.append(q_param.strip())
        elif re_fields.search(q_param):
            q_list.extend(
                i['op'] if 'op' in i else '{}:({})'.format(i['field'], i['value'])
                for i in parse_query_fields(q_param)
            )
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
                v = re_to_esc.sub(r'\\\g<0>', v)
                # Somehow v can be empty at this point,
                #   passing the following with empty strings causes a severe error in SOLR
                if v:
                    q_list.append(
                        "(author_name:({name}) OR author_alternative_name:({name}))".format(
                            name=v
                        )
                    )

        check_params = [
            'title',
            'publisher',
            'oclc',
            'lccn',
            'contributor',
            'subject',
            'place',
            'person',
            'time',
        ]
        q_list += [
            '{}:({})'.format(k, re_to_esc.sub(r'\\\g<0>', param[k]))
            for k in check_params
            if k in param
        ]
        if param.get('isbn'):
            q_list.append(
                'isbn:(%s)' % (normalize_isbn(param['isbn']) or param['isbn'])
            )
    return (q_list, use_dismax)


def execute_solr_query(
    solr_path: str, params: Union[dict, list[tuple[str, Any]]]
) -> Optional[Response]:
    stats.begin("solr", url=f'{solr_path}?{urlencode(params)}')
    try:
        response = requests.get(solr_path, params=params, timeout=10)
        response.raise_for_status()
    except requests.HTTPError:
        logger.exception("Failed solr query")
        return None
    finally:
        stats.end()
    return response


def parse_json_from_solr_query(
    solr_path: str, params: Union[dict, list[tuple[str, Any]]]
) -> Optional[dict]:
    """
    Returns a json.loaded Python object or None
    """
    response = execute_solr_query(solr_path, params)
    if not response:
        logger.error("Error parsing empty search engine response")
        return None
    try:
        return response.json()
    except JSONDecodeError:
        logger.exception("Error parsing search engine response")
        return None


def run_solr_query(
    param=None,
    rows=100,
    page=1,
    sort=None,
    spellcheck_count=None,
    offset=None,
    fields=None,
    facet=True,
):
    param = param or {}

    # use page when offset is not specified
    if offset is None:
        offset = rows * (page - 1)

    (q_list, use_dismax) = build_q_list(param)
    params = [
        ('fl', ','.join(fields or DEFAULT_SEARCH_FIELDS)),
        ('fq', 'type:work'),
        ('q.op', 'AND'),
        ('start', offset),
        ('rows', rows),
    ]

    if spellcheck_count is None:
        spellcheck_count = default_spellcheck_count

    if spellcheck_count:
        params.append(('spellcheck', 'true'))
        params.append(('spellcheck.count', spellcheck_count))

    if facet:
        params.append(('facet', 'true'))
        for facet in FACET_FIELDS:
            params.append(('facet.field', facet))

    if q_list:
        if use_dismax:
            params.append(('q', ' '.join(q_list)))
            params.append(('defType', 'dismax'))
            params.append(('qf', 'text title^20 author_name^20'))
            params.append(('bf', 'min(100,edition_count)'))
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
        params += [('fq', f'{field}:"{val}"') for val in values if val]

    if sort:
        params.append(('sort', sort))

    if 'wt' in param:
        params.append(('wt', param.get('wt')))
    url = f'{solr_select_url}?{urlencode(params)}'

    response = execute_solr_query(solr_select_url, params)
    solr_result = response.content if response else None  # bytes or None
    return (solr_result, url, q_list)


def do_search(param, sort, page=1, rows=100, spellcheck_count=None):
    if sort:
        sort = process_sort(sort)
    (solr_result, solr_select, q_list) = run_solr_query(
        param, rows, page, sort, spellcheck_count
    )
    is_bad = False
    if not solr_result or solr_result.startswith(b'<html'):
        is_bad = True
    if not is_bad:
        try:
            root = XML(solr_result)
        except XMLSyntaxError:
            is_bad = True
    if is_bad:
        m = re_pre.search(solr_result)
        return web.storage(
            facet_counts=None,
            docs=[],
            is_advanced=bool(param.get('q')),
            num_found=None,
            solr_select=solr_select,
            q_list=q_list,
            error=(web.htmlunquote(m.group(1)) if m else solr_result),
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
        facet_counts=read_facets(root),
        docs=docs,
        is_advanced=bool(param.get('q')),
        num_found=(int(docs.attrib['numFound']) if docs is not None else None),
        solr_select=solr_select,
        q_list=q_list,
        error=None,
        spellcheck=spell_map,
    )


def get_doc(doc):  # called from work_search template
    e_ia = doc.find("arr[@name='ia']")
    e_id_project_gutenberg = doc.find("arr[@name='id_project_gutenberg']") or []
    e_id_librivox = doc.find("arr[@name='id_librivox']") or []
    e_id_standard_ebooks = doc.find("arr[@name='id_standard_ebooks']") or []
    e_id_openstax = doc.find("arr[@name='id_openstax']") or []

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
        authors = [
            web.storage(
                key=key,
                name=name,
                url="/authors/{}/{}".format(
                    key, (urlsafe(name) if name is not None else 'noname')
                ),
            )
            for key, name in zip(ak, an)
        ]
    cover = doc.find("str[@name='cover_edition_key']")
    languages = doc.find("arr[@name='language']")
    e_public_scan = doc.find("bool[@name='public_scan_b']")
    e_lending_edition = doc.find("str[@name='lending_edition_s']")
    e_lending_identifier = doc.find("str[@name='lending_identifier_s']")
    e_collection = doc.find("str[@name='ia_collection_s']")
    collections = set()
    if e_collection is not None:
        collections = set(e_collection.text.split(';'))

    doc = web.storage(
        key=doc.find("str[@name='key']").text,
        title=doc.find("str[@name='title']").text,
        edition_count=int(doc.find("int[@name='edition_count']").text),
        ia=[e.text for e in (e_ia if e_ia is not None else [])],
        has_fulltext=(doc.find("bool[@name='has_fulltext']").text == 'true'),
        public_scan=(
            (e_public_scan.text == 'true')
            if e_public_scan is not None
            else (e_ia is not None)
        ),
        lending_edition=(
            e_lending_edition.text if e_lending_edition is not None else None
        ),
        lending_identifier=(
            e_lending_identifier.text if e_lending_identifier is not None else None
        ),
        collections=collections,
        authors=authors,
        first_publish_year=first_pub,
        first_edition=first_edition,
        subtitle=work_subtitle,
        cover_edition_key=(cover.text if cover is not None else None),
        languages=languages and [lang.text for lang in languages],
        id_project_gutenberg=[e.text for e in e_id_project_gutenberg],
        id_librivox=[e.text for e in e_id_librivox],
        id_standard_ebooks=[e.text for e in e_id_standard_ebooks],
        id_openstax=[e.text for e in e_id_openstax],
    )

    doc.url = doc.key + '/' + urlsafe(doc.title)
    return doc


def work_object(w):  # called by works_by_author
    ia = w.get('ia', [])
    obj = dict(
        authors=[
            web.storage(key='/authors/' + k, name=n)
            for k, n in zip(w['author_key'], w['author_name'])
        ],
        edition_count=w['edition_count'],
        key=w['key'],
        title=w['title'],
        public_scan=w.get('public_scan_b', bool(ia)),
        lending_edition=w.get('lending_edition_s', ''),
        lending_identifier=w.get('lending_identifier_s', ''),
        collections=set(
            w['ia_collection_s'].split(';') if 'ia_collection_s' in w else []
        ),
        url=w['key'] + '/' + urlsafe(w['title']),
        cover_edition_key=w.get('cover_edition_key'),
        first_publish_year=(
            w['first_publish_year'] if 'first_publish_year' in w else None
        ),
        ia=w.get('ia', []),
        cover_i=w.get('cover_i'),
        id_project_gutenberg=w.get('id_project_gutenberg'),
        id_librivox=w.get('id_librivox'),
        id_standard_ebooks=w.get('id_standard_ebooks'),
        id_openstax=w.get('id_openstax'),
    )

    for f in 'has_fulltext', 'subtitle':
        if w.get(f):
            obj[f] = w[f]
    return web.storage(obj)


class scan(delegate.page):
    """
    Experimental EAN barcode scanner page to scan and add/view books by their barcodes.
    """

    path = "/barcodescanner"

    def GET(self):
        return render.barcodescanner()


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
                if len(clean) == 1 and clean[0] == '':
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

        i = web.input(
            author_key=[],
            language=[],
            first_publish_year=[],
            publisher_facet=[],
            subject_facet=[],
            person_facet=[],
            place_facet=[],
            time_facet=[],
            public_scan_b=[],
        )

        # Send to full-text Search Inside if checkbox checked
        if i.get('search-fulltext'):
            raise web.seeother(
                '/search/inside?' + urllib.parse.urlencode({'q': i.get('q', '')})
            )

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
                raise web.seeother(f'/{OLID_URLS[m.group(1)]}/{q}')
            m = re_isbn_field.match(q)
            if m:
                self.isbn_redirect(m.group(1))
            q_list.append(q)
        for k in ('title', 'author', 'isbn', 'subject', 'place', 'person', 'publisher'):
            if k in i:
                v = re_to_esc.sub(r'\\\g<0>', i[k].strip())
                q_list.append(k + ':' + v)
        return render.work_search(
            i,
            ' '.join(q_list),
            do_search,
            get_doc,
            get_availability_of_ocaids,
            fulltext_search,
            FACET_FIELDS,
        )


def works_by_author(
    akey, sort='editions', page=1, rows=100, has_fulltext=False, query=None
):
    # called by merge_author_works
    q = 'author_key:' + akey
    if query:
        q = query

    offset = rows * (page - 1)
    params = [
        ('fq', 'author_key:' + akey),
        ('fq', 'type:work'),
        ('q', q),
        ('start', offset),
        ('rows', rows),
        (
            'fl',
            ','.join(
                [
                    'key',
                    'author_name',
                    'author_key',
                    'title',
                    'subtitle',
                    'edition_count',
                    'ia',
                    'cover_edition_key',
                    'has_fulltext',
                    'language',
                    'first_publish_year',
                    'public_scan_b',
                    'lending_edition_s',
                    'lending_identifier_s',
                    'ia_collection_s',
                    'id_project_gutenberg',
                    'id_librivox',
                    'id_standard_ebooks',
                    'id_openstax',
                    'cover_i',
                ]
            ),
        ),
        ('wt', 'json'),
        ('q.op', 'AND'),
        ('facet', 'true'),
        ('facet.mincount', 1),
        ('f.author_facet.facet.sort', 'count'),
        ('f.publish_year.facet.limit', -1),
        ('facet.limit', 25),
    ]

    if has_fulltext:
        params.append(('fq', 'has_fulltext:true'))

    if sort == "editions":
        params.append(('sort', 'edition_count desc'))
    elif sort.startswith('old'):
        params.append(('sort', 'first_publish_year asc'))
    elif sort.startswith('new'):
        params.append(('sort', 'first_publish_year desc'))
    elif sort.startswith('title'):
        params.append(('sort', 'title asc'))

    facet_fields = [
        "author_facet",
        "language",
        "publish_year",
        "publisher_facet",
        "subject_facet",
        "person_facet",
        "place_facet",
        "time_facet",
    ]
    for f in facet_fields:
        params.append(("facet.field", f))

    reply = parse_json_from_solr_query(solr_select_url, params)
    if reply is None:
        return web.storage(
            num_found=0,
            works=[],
            years=[],
            get_facet=[],
            sort=sort,
        )
    # TODO: Deep JSON structure defense - for now, let it blow up so easier to detect
    facets = reply['facet_counts']['facet_fields']
    works = [work_object(w) for w in reply['response']['docs']]

    def get_facet(f, limit=None):
        return list(web.group(facets[f][: limit * 2] if limit else facets[f], 2))

    return web.storage(
        num_found=int(reply['response']['numFound']),
        works=add_availability(works),
        years=[(int(k), v) for k, v in get_facet('publish_year')],
        get_facet=get_facet,
        sort=sort,
    )


def sorted_work_editions(wkey, json_data=None):
    """Setting json_data to a real value simulates getting SOLR data back, i.e. for testing (but ick!)"""
    q = 'key:' + wkey
    if json_data:
        reply = json.loads(json_data)
    else:
        reply = parse_json_from_solr_query(
            solr_select_url,
            {
                'q.op': 'AND',
                'q': q,
                'rows': 10,
                'fl': 'edition_key',
                'qt': 'standard',
                'wt': 'json',
            },
        )
    if reply is None or reply.get('response', {}).get('numFound', 0) == 0:
        return []
    # TODO: Deep JSON structure defense - for now, let it blow up so easier to detect
    return reply["response"]['docs'][0].get('edition_key', [])


def top_books_from_author(akey, rows=5, offset=0):
    q = 'author_key:(' + akey + ')'
    json_result = parse_json_from_solr_query(
        solr_select_url,
        {
            'q': q,
            'start': offset,
            'rows': rows,
            'fl': 'key,title,edition_count,first_publish_year',
            'sort': 'edition_count desc',
            'wt': 'json',
        },
    )
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
        return render_template("search/advancedsearch.html")


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


def run_solr_search(solr_select: str, params: dict):
    response = execute_solr_query(solr_select, params)
    json_data = response.content if response else None  # bytes or None
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
            error = error[len(solr_error) :]
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

        keys = web.ctx.site.things(
            {
                "type": "/type/list",
                "name~": q,
                "limit": int(limit),
                "offset": int(offset),
            }
        )

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

        response = {'start': offset, 'docs': [doc.preview() for doc in docs]}

        web.header('Content-Type', 'application/json')
        return delegate.RawText(json.dumps(response))


class subject_search(delegate.page):
    path = '/search/subjects'

    def GET(self):
        return render_template('search/subjects.tmpl', self.get_results)

    def get_results(self, q, offset=0, limit=100):
        valid_fields = ['key', 'name', 'subject_type', 'work_count']
        q = escape_colon(escape_bracket(q), valid_fields)

        results = run_solr_search(
            solr_select_url,
            {
                "fq": "type:subject",
                "q.op": "AND",
                "q": q,
                "start": offset,
                "rows": limit,
                "fl": ",".join(valid_fields),
                "qt": "standard",
                "wt": "json",
                "sort": "work_count desc",
            },
        )
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
        valid_fields = [
            'key',
            'name',
            'alternate_names',
            'birth_date',
            'death_date',
            'date',
            'work_count',
        ]
        q = escape_colon(escape_bracket(q), valid_fields)
        q_has_fields = ':' in q.replace(r'\:', '') or '*' in q

        d = run_solr_search(
            solr_select_url,
            {
                'fq': 'type:author',
                'q.op': 'AND',
                'q': q,
                'start': offset,
                'rows': limit,
                'fl': '*',
                'qt': 'standard',
                'sort': 'work_count desc',
                'wt': 'json',
                **(
                    {}
                    if q_has_fields
                    else {'defType': 'dismax', 'qf': 'name alternate_names'}
                ),
            },
        )

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
        limit = min(1000, limit)  # limit limit to 1000.

        response = self.get_results(i.q, offset=offset, limit=limit)['response']
        web.header('Content-Type', 'application/json')
        return delegate.RawText(json.dumps(response))


@public
def random_author_search(limit=10):
    """
    Returns a dict that contains a random list of authors.  Amount of authors
    returned is set be the given limit.
    """
    letters_and_digits = string.ascii_letters + string.digits
    seed = ''.join(random.choice(letters_and_digits) for _ in range(10))

    search_results = run_solr_search(
        solr_select_url,
        {
            'q': 'type:author',
            'rows': limit,
            'sort': f'random_{seed} desc',
            'wt': 'json',
        },
    )

    docs = search_results.get('response', {}).get('docs', [])

    assert docs, f"random_author_search({limit}) returned no docs"
    assert (
        len(docs) == limit
    ), f"random_author_search({limit}) returned {len(docs)} docs"

    for doc in docs:
        # replace /authors/OL1A with OL1A
        # The template still expects the key to be in the old format
        doc['key'] = doc['key'].split("/")[-1]

    return search_results['response']


def rewrite_list_query(q, page, offset, limit):
    """Takes a solr query. If it doesn't contain a /lists/ key, then
    return the query, unchanged, exactly as it entered the
    function. If it does contain a lists key, then use the pagination
    information to fetch the right block of keys from the
    lists_editions and lists_works API and then feed these editions resulting work
    keys into solr with the form key:(OL123W, OL234W). This way, we
    can use the solr API to fetch list works and render them in
    carousels in the right format.
    """
    def cached_get_list_book_keys(key, offset, limit):
        # make cacheable
        if 'env' not in web.ctx:
            delegate.fakeload()
        lst = web.ctx.site.get(key)
        return lst.get_book_keys(offset=offset, limit=limit)

    if '/lists/' in q:
        # we're making an assumption that q is just a list key
        book_keys = cache.memcache_memoize(
            cached_get_list_book_keys,
            "search.list_books_query",
            timeout=5*60)(q, offset, limit)

        q = f"key:({' OR '.join(book_keys)})"

        # We've applied the offset to fetching get_list_editions to
        # produce the right set of discrete work IDs. We don't want
        # it applied to paginate our resulting solr query.
        offset = 0
        page = 1
    return q, page, offset, limit


@public
def work_search(
    query,
    sort=None,
    page=1,
    offset=0,
    limit=100,
    fields='*',
    facet=True,
    spellcheck_count=None,
):
    """
    params:
    query: dict
    sort: str editions|old|new|scans
    """
    # Ensure we don't mutate the `query` passed in by reference
    query = copy.deepcopy(query)
    query['wt'] = 'json'
    if sort:
        sort = process_sort(sort)

    # deal with special /lists/ key queries
    query['q'], page, offset, limit = rewrite_list_query(
        query['q'], page, offset, limit
    )
    try:
        (reply, solr_select, q_list) = run_solr_query(
            query,
            rows=limit,
            page=page,
            sort=sort,
            offset=offset,
            fields=fields,
            facet=facet,
            spellcheck_count=spellcheck_count,
        )
        response = json.loads(reply)['response'] or ''
    except (ValueError, OSError) as e:
        logger.error("Error in processing search API.")
        response = dict(start=0, numFound=0, docs=[], error=str(e))

    # backward compatibility
    response['num_found'] = response['numFound']
    if fields == '*' or 'availability' in fields:
        response['docs'] = add_availability(response['docs'])
    return response


class search_json(delegate.page):
    path = "/search"
    encoding = "json"

    def GET(self):
        i = web.input(
            author_key=[],
            subject_facet=[],
            person_facet=[],
            place_facet=[],
            time_facet=[],
            first_publish_year=[],
            publisher_facet=[],
            language=[],
            public_scan_b=[],
        )
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

        fields = query.pop('fields', '*').split(',')
        facet = query.pop('_facet', 'true').lower() in ['true']
        spellcheck_count = safeint(
            query.pop("_spellcheck_count", default_spellcheck_count),
            default=default_spellcheck_count,
        )

        # If the query is a /list/ key, create custom list_editions_query
        q = query.get('q', '')
        query['q'], page, offset, limit = rewrite_list_query(
            q, page, offset, limit
        )
        response = work_search(
            query,
            sort=sort,
            page=page,
            offset=offset,
            limit=limit,
            fields=fields,
            facet=facet,
            spellcheck_count=spellcheck_count,
        )
        response['q'] = q
        response['offset'] = offset
        response['docs'] = response['docs']
        web.header('Content-Type', 'application/json')
        return delegate.RawText(json.dumps(response, indent=4))


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
