import copy
import functools
import itertools
import json
import logging
import re
import time
import urllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast
from unicodedata import normalize

import httpx
import web
from requests import Response
from typing_extensions import deprecated

from infogami import config
from infogami.infobase.client import storify
from infogami.utils import delegate
from infogami.utils.view import public, render, render_template, safeint
from openlibrary.core import cache
from openlibrary.core.lending import add_availability
from openlibrary.core.models import Edition
from openlibrary.i18n import gettext as _
from openlibrary.plugins.openlibrary.processors import urlsafe
from openlibrary.plugins.upstream.utils import (
    get_language_name,
    safeget,
    urlencode,
)
from openlibrary.plugins.worksearch.schemes import SearchScheme
from openlibrary.plugins.worksearch.schemes.authors import AuthorSearchScheme
from openlibrary.plugins.worksearch.schemes.editions import EditionSearchScheme
from openlibrary.plugins.worksearch.schemes.lists import ListSearchScheme
from openlibrary.plugins.worksearch.schemes.subjects import SubjectSearchScheme
from openlibrary.plugins.worksearch.schemes.works import (
    WorkSearchScheme,
    has_solr_editions_enabled,
)
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.solr.query_utils import fully_escape_query
from openlibrary.solr.solr_types import SolrDocument
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.isbn import normalize_isbn
from openlibrary.utils.solr import (
    DEFAULT_PASS_TIME_ALLOWED,
    DEFAULT_SOLR_TIMEOUT_SECONDS,
    SolrRequestLabel,
)

logger = logging.getLogger("openlibrary.worksearch")


OLID_URLS = {'A': 'authors', 'M': 'books', 'W': 'works'}

re_isbn_field = re.compile(r'^\s*(?:isbn[:\s]*)?([-0-9X]{9,})\s*$', re.IGNORECASE)
re_olid = re.compile(r'^OL\d+([AMW])$')

plurals = {f + 's': f for f in ('publisher', 'author')}

default_spellcheck_count = 10
if hasattr(config, 'plugin_worksearch'):
    solr_select_url = (
        config.plugin_worksearch.get('solr_base_url', 'localhost') + '/select'
    )

    default_spellcheck_count = config.plugin_worksearch.get('spellcheck_count', 10)


@public
def get_facet_map() -> tuple[tuple[str, str]]:
    return (
        ('has_fulltext', _('eBook?')),
        ('language', _('Language')),
        ('author_key', _('Author')),
        ('subject_facet', _('Subjects')),
        ('first_publish_year', _('First published')),
        ('publisher_facet', _('Publisher')),
        ('person_facet', _('People')),
        ('place_facet', _('Places')),
        ('time_facet', _('Times')),
        ('public_scan_b', _('Classic eBooks')),
    )


@public
def get_solr_works(
    work_keys: set[str], fields: Iterable[str] | None = None, editions=False
) -> dict[str, web.storage]:
    from openlibrary.plugins.worksearch.search import get_solr

    if not fields:
        fields = WorkSearchScheme.default_fetched_fields | {'editions', 'providers'}

    if editions:
        # To get the top matching edition, need to do a proper query
        resp = run_solr_query(
            WorkSearchScheme(),
            {'q': 'key:(%s)' % ' OR '.join(work_keys)},
            rows=len(work_keys),
            fields=list(fields),
            facet=False,
        )
        return {
            # storify isn't typed properly, but basically recursively call web.storage
            doc['key']: cast(web.storage, storify(doc))
            for doc in resp.docs
        }
    else:
        return {doc['key']: doc for doc in get_solr().get_many(work_keys, fields)}


def read_author_facet(author_facet: str) -> tuple[str, str]:
    """
    >>> read_author_facet("OL26783A Leo Tolstoy")
    ('OL26783A', 'Leo Tolstoy')
    """
    key, name = author_facet.split(' ', 1)
    return key, name


def process_facet(
    field: str, facets: Iterable[tuple[str, int]]
) -> tuple[str, str, int]:
    if field == 'has_fulltext':
        counts = dict(facets)
        yield ('true', 'yes', counts.get('true', 0))
        yield ('false', 'no', counts.get('false', 0))
    else:
        for val, count in facets:
            if count == 0:
                continue
            if field == 'author_key':
                key, name = read_author_facet(val)
                yield (key, name, count)
            elif field == 'language':
                yield (
                    val,
                    get_language_name(f'/languages/{val}', web.ctx.lang or 'en'),
                    count,
                )
            else:
                yield (val, val, count)


def process_facet_counts(
    facet_counts: dict[str, list],
) -> dict[str, tuple[str, str, int]]:
    for field, facets in facet_counts.items():
        if field == 'author_facet':
            field = 'author_key'
        yield field, list(process_facet(field, web.group(facets, 2)))


async def async_execute_solr_query(
    solr_path: str,
    params: dict | list[tuple[str, Any]],
    _timeout: int | None = DEFAULT_SOLR_TIMEOUT_SECONDS,
    _pass_time_allowed: bool = DEFAULT_PASS_TIME_ALLOWED,
) -> httpx.Response | None:
    url = solr_path
    if params:
        url += '&' if '?' in url else '?'
        url += urlencode(params)

    try:
        response = await get_solr().raw_request(
            solr_path,
            urlencode(params),
            _timeout=_timeout,
            _pass_time_allowed=_pass_time_allowed,
        )
    except httpx.HTTPError:
        logger.exception("Failed solr query")
        return None
    return response


execute_solr_query = async_bridge.wrap(async_execute_solr_query)

# Expose this publicly
public(has_solr_editions_enabled)


@public
def get_remembered_layout():
    def read_query_string():
        return web.input(layout=None).get('layout')

    def read_cookie():
        if "LBL" in web.ctx.env.get("HTTP_COOKIE", ""):
            return web.cookies().get('LBL')

    if (qs_value := read_query_string()) is not None:
        return qs_value

    if (cookie_value := read_cookie()) is not None:
        return cookie_value

    return 'details'


def _prepare_solr_query_params(  # noqa: PLR0912
    scheme: SearchScheme,
    param: dict | None = None,
    rows=100,
    page=1,
    sort: str | None = None,
    spellcheck_count=None,
    offset=None,
    fields: str | list[str] | None = None,
    facet: bool | Iterable[str] = True,
    highlight: bool = False,
    allowed_filter_params: set[str] | None = None,
    extra_params: list[tuple[str, Any]] | None = None,
    request_label: SolrRequestLabel = 'UNLABELLED',
) -> tuple[list[tuple[str, Any]], list[str]]:
    """
    :param param: dict of query parameters
    Prepares the list of parameters for a Solr query, encapsulating the business logic.
    """
    param = param or {}

    if not fields:
        fields = []
    elif isinstance(fields, str):
        fields = fields.split(',')

    # use page when offset is not specified
    if offset is None:
        offset = rows * (page - 1)

    params = [
        *(('fq', subquery) for subquery in scheme.universe),
        ('start', offset),
        ('rows', rows),
        ('ol.label', request_label),
        ('wt', param.get('wt', 'json')),
    ] + (extra_params or [])

    if spellcheck_count is None:
        spellcheck_count = default_spellcheck_count

    if spellcheck_count:
        params.append(('spellcheck', 'true'))
        params.append(('spellcheck.count', spellcheck_count))

    facet_fields = scheme.facet_fields if isinstance(facet, bool) else facet
    if facet and facet_fields:
        params.append(('facet', 'true'))
        for facet in facet_fields:  # noqa: PLR1704
            if isinstance(facet, str):
                params.append(('facet.field', facet))
            elif isinstance(facet, dict):
                params.append(('facet.field', facet['name']))
                if 'sort' in facet:
                    params.append((f'f.{facet["name"]}.facet.sort', facet['sort']))
                if 'limit' in facet:
                    params.append((f'f.{facet["name"]}.facet.limit', facet['limit']))
            else:
                # Should never get here
                raise ValueError(f'Invalid facet type: {facet}')

    facet_params = (allowed_filter_params or set(scheme.facet_fields)) & set(param)
    for (field, value), rewrite in scheme.facet_rewrites.items():
        if param.get(field) == value:
            if field in facet_params:
                facet_params.remove(field)
            params.append(('fq', rewrite() if callable(rewrite) else rewrite))

    for field in facet_params:
        if field == 'author_facet':
            field = 'author_key'
        values = param[field]
        if isinstance(values, str):
            values = [values]
        params += [('fq', f'{field}:"{val}"') for val in values if val]

    # Many fields in solr use the convention of `*_facet` both
    # as a facet key and as the explicit search query key.
    # Examples being publisher_facet, subject_facet?
    # `author_key` & `author_facet` is an example of a mismatch that
    # breaks this rule. This code makes it so, if e.g. `author_facet` is used where
    # `author_key` is intended, both will be supported (and vis versa)
    # This "doubling up" has no real performance implication
    # but does fix cases where the search query is different than the facet names
    q = None
    if param.get('q'):
        q = scheme.process_user_query(param['q'])

    if params_q := scheme.build_q_from_params(param):
        q = f'{q} {params_q}' if q else params_q

    if q:
        solr_fields = (
            set(fields or scheme.default_fetched_fields) - scheme.non_solr_fields
        )
        if 'editions' in solr_fields:
            solr_fields.remove('editions')
            solr_fields.add('editions:[subquery]')
        if ed_sort := param.get('editions.sort'):
            params.append(
                ('editions.sort', EditionSearchScheme().process_user_sort(ed_sort))
            )
        params.append(('fl', ','.join(solr_fields)))
        params += scheme.q_to_solr_params(q, solr_fields, params, highlight=highlight)

    if sort:
        params.append(('sort', scheme.process_user_sort(sort)))

    return params, fields


def _process_solr_response_and_enrich(
    response: Response | None,
    scheme: SearchScheme,
    fields: list[str],
    sort: str | None,
    url: str,
    duration: float,
) -> 'SearchResponse':
    """
    Processes the Solr response, enriches it, and returns a SearchResponse object.
    """
    solr_result = response.json() if response is not None else None

    if safeget(lambda: solr_result['response']['docs']):
        non_solr_fields = set(fields) & scheme.non_solr_fields
        if non_solr_fields:
            scheme.add_non_solr_fields(non_solr_fields, solr_result)

    return SearchResponse.from_solr_result(solr_result, sort, url, time=duration)


def run_solr_query(
    scheme: SearchScheme,
    param: dict | None = None,
    rows=100,
    page=1,
    sort: str | None = None,
    spellcheck_count=None,
    offset=None,
    fields: str | list[str] | None = None,
    facet: bool | Iterable[str] = True,
    highlight: bool = False,
    allowed_filter_params: set[str] | None = None,
    extra_params: list[tuple[str, Any]] | None = None,
    request_label: SolrRequestLabel = 'UNLABELLED',
) -> 'SearchResponse':
    """
    Builds and executes a synchronous Solr query.
    """
    params, fields = _prepare_solr_query_params(
        scheme,
        param,
        rows=rows,
        page=page,
        sort=sort,
        spellcheck_count=spellcheck_count,
        offset=offset,
        fields=fields,
        facet=facet,
        highlight=highlight,
        allowed_filter_params=allowed_filter_params,
        extra_params=extra_params,
        request_label=request_label,
    )

    url = f'{solr_select_url}?{urlencode(params)}'
    start_time = time.time()
    response = execute_solr_query(solr_select_url, params)
    end_time = time.time()
    duration = end_time - start_time

    return _process_solr_response_and_enrich(
        response, scheme, fields, sort, url, duration
    )


async def async_run_solr_query(
    scheme: SearchScheme,
    param: dict | None = None,
    **kwargs,
) -> 'SearchResponse':
    """
    Builds and executes an asynchronous Solr query.
    """
    params, fields = _prepare_solr_query_params(scheme, param, **kwargs)

    url = f'{solr_select_url}?{urlencode(params)}'
    start_time = time.time()
    response = await async_execute_solr_query(solr_select_url, params)
    end_time = time.time()
    duration = end_time - start_time

    return _process_solr_response_and_enrich(
        response, scheme, fields, kwargs.get('sort'), url, duration
    )


@functools.cache
def load_stopwords(lang: str = 'en') -> set[str]:
    """
    Load stop words for a given language
    """
    try:
        with Path(f'conf/solr/conf/lang/stopwords_{lang}.txt').open() as f:
            return {
                line.strip() for line in f if line.strip() and not line.startswith('#')
            }
    except FileNotFoundError:
        logger.warning(f"Stopwords file not found for language: {lang}")
        return set()


@dataclass
class SearchResponse:
    facet_counts: dict[str, list[tuple[str, str, int]]]
    sort: str
    docs: list
    num_found: int
    solr_select: str
    raw_resp: dict = None
    highlighting: dict[str, dict[str, list[str]]] | None = None
    error: str = None
    time: float = None
    """Seconds to execute the query"""

    @staticmethod
    def from_solr_result(
        solr_result: dict | None,
        sort: str,
        solr_select: str,
        time: float,
    ) -> 'SearchResponse':
        if not solr_result or 'error' in solr_result:
            return SearchResponse(
                facet_counts=None,
                sort=sort,
                docs=[],
                num_found=None,
                solr_select=solr_select,
                error=(solr_result.get('error') if solr_result else None),
                time=time,
            )
        else:
            if highlighting := solr_result.get('highlighting'):
                highlighting = SearchResponse.clean_highlighting(highlighting)
            return SearchResponse(
                facet_counts=(
                    dict(
                        process_facet_counts(
                            solr_result['facet_counts']['facet_fields']
                        )
                    )
                    if 'facet_counts' in solr_result
                    else None
                ),
                sort=sort,
                raw_resp=solr_result,
                docs=solr_result['response']['docs'],
                num_found=solr_result['response']['numFound'],
                highlighting=highlighting,
                solr_select=solr_select,
                time=time,
            )

    @staticmethod
    def clean_highlighting(
        highlighting: dict[str, dict[str, list[str]]],
    ) -> dict[str, dict[str, list[str]]] | None:
        """
        Remove highlight fragments that only contain stop words, and sort by most matches.

        :param highlighting: solr highlighting response. e.g. {'OL123W': {'title': ['<em>title</em>']}}

        NOTE: This _should_ be handled by solr automatically, but we had to disable stopwords in solr
        due to a bug. See https://github.com/internetarchive/openlibrary/issues/5393

        >>> highlighting = {'OL123W': {'title': ['<em>title</em>']}}
        >>> SearchResponse.clean_highlighting(highlighting)
        {'OL123W': {'title': ['<em>title</em>']}}

        >>> highlighting = {'OL123W': {'title': ['<em>the</em> <em>title</em>']}}
        >>> SearchResponse.clean_highlighting(highlighting)
        {'OL123W': {'title': ['<em>the</em> <em>title</em>']}}

        >>> highlighting = {'OL123W': {'title': ['<em>the</em> title']}}
        >>> SearchResponse.clean_highlighting(highlighting)

        >>> highlighting = {'OL123W': {'title': ['<em>The</em> title', 'a <em>foobar</em>']}}
        >>> SearchResponse.clean_highlighting(highlighting)
        {'OL123W': {'title': ['a <em>foobar</em>']}}
        """

        def get_matches(fragment: str) -> set[str]:
            # Note: Solr has one wrapping `<em>` per word, even if they are adjacent
            # Note: The Solr response is correctly html escaped, so there should be
            # no `<` in between the `<em>` tags since they are escaped to `&lt;`
            return {word.lower() for word in re.findall(r'<em>([^<]+)</em>', fragment)}

        # For now just to English? In future we might support other languages, but it's unclear
        # which language to use; the book's language or the user's language?
        stopwords = load_stopwords('en')
        for key in list(highlighting):
            highlights = highlighting[key]

            for field in list(highlights):
                highlights[field] = [
                    term for term in highlights[field] if get_matches(term) - stopwords
                ]

                # Sort by most matches
                highlights[field].sort(
                    key=lambda term: len(get_matches(term)), reverse=True
                )

                # Remove empty
                if not highlights[field]:
                    del highlights[field]

            if not highlights:
                del highlighting[key]

        return highlighting or None


def do_search(
    param: dict,
    sort: str | None,
    page=1,
    rows=100,
    facet=False,
    highlight=False,
    spellcheck_count=None,
    request_label: SolrRequestLabel = 'UNLABELLED',
):
    """
    :param param: dict of search url parameters
    :param sort: csv sort ordering
    :param spellcheck_count: Not really used; should probably drop
    """
    # If you want work_search page html to extend default_fetched_fields:
    extra_fields = {
        'editions',
        'providers',
        'ratings_average',
        'ratings_count',
        'want_to_read_count',
    }
    if sort and 'trending' in sort:
        extra_fields.add('trending_*')
    fields = WorkSearchScheme.default_fetched_fields | extra_fields

    if web.cookies(sfw="").sfw == 'yes':
        fields |= {'subject'}

    return run_solr_query(
        WorkSearchScheme(),
        param,
        rows,
        page,
        sort,
        spellcheck_count,
        fields=list(fields),
        facet=facet,
        highlight=highlight,
        request_label=request_label,
    )


def get_doc(doc: SolrDocument):
    """
    Coerce a solr document to look more like an Open Library edition/work. Ish.

    called from work_search template
    """
    result = web.storage(
        key=doc['key'],
        title=doc['title'],
        url=f"{doc['key']}/{urlsafe(doc['title'])}",
        edition_count=doc['edition_count'],
        ia=doc.get('ia', []),
        collections=(doc.get('ia_collection') or []),
        has_fulltext=doc.get('has_fulltext', False),
        public_scan=doc.get('public_scan_b', bool(doc.get('ia'))),
        lending_edition=doc.get('lending_edition_s', None),
        lending_identifier=doc.get('lending_identifier_s', None),
        authors=[
            web.storage(
                key=key,
                name=name,
                url=f"/authors/{key}/{urlsafe(name or 'noname')}",
                birth_date=doc.get('birth_date', None),
                death_date=doc.get('death_date', None),
            )
            for key, name in zip(doc.get('author_key', []), doc.get('author_name', []))
        ],
        series=[
            web.storage(
                series=web.storage(
                    key=key,
                    name=name,
                ),
                position=position,
            )
            for key, name, position in zip(
                doc.get('series_key', []),
                doc.get('series_name', []),
                doc.get('series_position', []),
            )
        ],
        first_publish_year=doc.get('first_publish_year', None),
        first_edition=doc.get('first_edition', None),
        subtitle=doc.get('subtitle', None),
        cover_edition_key=doc.get('cover_edition_key', None),
        languages=doc.get('language', []),
        id_project_gutenberg=doc.get('id_project_gutenberg', []),
        id_project_runeberg=doc.get('id_project_runeberg', []),
        id_librivox=doc.get('id_librivox', []),
        id_standard_ebooks=doc.get('id_standard_ebooks', []),
        id_openstax=doc.get('id_openstax', []),
        id_cita_press=doc.get('id_cita_press', []),
        id_wikisource=doc.get('id_wikisource', []),
        editions=[
            web.storage(
                {
                    **ed,
                    'title': ed.get('title', 'Untitled'),
                    'url': f"{ed['key']}/{urlsafe(ed.get('title', 'Untitled'))}",
                }
            )
            for ed in doc.get('editions', {}).get('docs', [])
        ],
        ratings_average=doc.get('ratings_average', None),
        ratings_count=doc.get('ratings_count', None),
        want_to_read_count=doc.get('want_to_read_count', None),
    )
    for field in doc:
        if field.startswith('trending_'):
            result[field] = doc[field]

    return result


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

        if ed := Edition.from_isbn(isbn):
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
        if q := i.get('q', '').strip():
            m = re_olid.match(q)
            if m:
                raise web.seeother(f'/{OLID_URLS[m.group(1)]}/{q}')
            m = re_isbn_field.match(q)
            if m:
                self.isbn_redirect(m.group(1))
            q_list.append(q)
        for k in ('title', 'author', 'isbn', 'subject', 'place', 'person', 'publisher'):
            if k in i:
                q_list.append(f'{k}:{fully_escape_query(i[k].strip())}')

        web_input = i
        param = {}
        for p in {
            'q',
            'title',
            'author',
            'page',
            'sort',
            'isbn',
            'oclc',
            'contributor',
            'publish_place',
            'lccn',
            'ia',
            'first_sentence',
            'publisher',
            'author_key',
            'debug',
            'subject',
            'place',
            'person',
            'time',
            'editions.sort',
        } | WorkSearchScheme.facet_fields:
            if web_input.get(p):
                param[p] = web_input[p]
        if list(param) == ['has_fulltext']:
            param = {}

        page = int(param.get('page', 1))
        sort = param.get('sort')
        rows = 20
        if param:
            search_response = do_search(
                param,
                sort,
                page,
                rows=rows,
                highlight=True,
                spellcheck_count=3,
                request_label='BOOK_SEARCH',
            )
        else:
            search_response = SearchResponse(
                facet_counts=None, sort='', docs=[], num_found=0, solr_select=''
            )
        return render.work_search(
            ' '.join(q_list),
            search_response,
            get_doc,
            param,
            page,
            rows,
        )


def works_by_author(
    akey: str,
    sort='editions',
    page=1,
    rows=100,
    facet=False,
    has_fulltext=False,
    query: str | None = None,
    request_label: SolrRequestLabel = 'UNLABELLED',
):
    param = {'q': query or '*:*'}
    if has_fulltext:
        param['has_fulltext'] = 'true'

    result = run_solr_query(
        WorkSearchScheme(),
        param=param,
        page=page,
        rows=rows,
        sort=sort,
        facet=(
            facet
            and [
                "subject_facet",
                "person_facet",
                "place_facet",
                "time_facet",
            ]
        ),
        request_label=request_label,
        fields=list(
            WorkSearchScheme.default_fetched_fields | {'editions', 'providers'}
        ),
        extra_params=[
            ('fq', f'author_key:{akey}'),
            ('facet.limit', 25),
        ],
    )

    result.docs = [get_doc(doc) for doc in result.docs]
    add_availability(
        [(work.get('editions') or [None])[0] or work for work in result.docs]
    )
    return result


def top_books_from_author(akey: str, rows=5) -> SearchResponse:
    return run_solr_query(
        WorkSearchScheme(),
        {'q': f'author_key:{akey}'},
        fields=['key', 'title', 'edition_count', 'first_publish_year'],
        sort='editions',
        rows=rows,
        facet=False,
    )


class advancedsearch(delegate.page):
    path = "/advancedsearch"

    def GET(self):
        return render_template("search/advancedsearch.html")


@dataclass
class ListSearchRequest:
    q: str
    offset: int
    limit: int
    page: int
    fields: str
    sort: str
    api: Literal['', 'next']

    @staticmethod
    def from_web_input(i: web.storage) -> 'ListSearchRequest':
        offset = safeint(i.get('offset', 0), 0)
        limit = safeint(i.get('limit', 20), 20)
        fields = i.get('fields', '')
        if i.get('api') != 'next':
            limit = min(1000, limit)
            fields = 'key'  # Just need the key since the old API fetches from DB
            if i.get('sort'):
                raise ValueError('sort not supported in the old API')

        if i.get('page'):
            page = safeint(i.page, 1)
            offset = limit * (page - 1)
        else:
            page = offset // limit + 1

        return ListSearchRequest(
            q=i.get('q', ''),
            offset=offset,
            limit=limit,
            page=page,
            fields=fields,
            sort=i.get('sort', ''),
            api=i.get('api', ''),
        )


# searches for lists and returns results in html format
class list_search(delegate.page):
    path = '/search/lists'

    def GET(self):  # referenced subject_search
        req = ListSearchRequest.from_web_input(web.input(api='next'))
        # Can't set fields when rendering html
        req.fields = 'key'
        resp = self.get_results(req, 'LIST_SEARCH')
        lists = list(web.ctx.site.get_many([doc['key'] for doc in resp.docs]))
        return render_template('search/lists.html', req, resp, lists)

    def get_results(
        self,
        req: ListSearchRequest,
        request_label: Literal['LIST_SEARCH', 'LIST_SEARCH_API'],
    ):
        return run_solr_query(
            ListSearchScheme(),
            {'q': req.q},
            offset=req.offset,
            rows=req.limit,
            fields=req.fields,
            sort=req.sort,
            request_label=request_label,
        )


# inherits from list_search but modifies the GET response to return results in JSON format
@deprecated('migrated to fastapi')
class list_search_json(list_search):
    # used subject_search_json as a reference
    path = '/search/lists'
    encoding = 'json'

    def GET(self):
        req = ListSearchRequest.from_web_input(web.input())
        resp = self.get_results(req, 'LIST_SEARCH_API')

        web.header('Content-Type', 'application/json')
        if req.api == 'next':
            # Match search.json
            return delegate.RawText(
                json.dumps(
                    {
                        'numFound': resp.num_found,
                        'num_found': resp.num_found,
                        'start': req.offset,
                        'q': req.q,
                        'docs': resp.docs,
                    }
                )
            )
        else:
            # Default to the old API shape for a while, then we'll flip
            return delegate.RawText(
                json.dumps(
                    {
                        'start': req.offset,
                        'docs': [
                            lst.preview()
                            for lst in web.ctx.site.get_many(
                                [doc['key'] for doc in resp.docs]
                            )
                        ],
                    }
                )
            )


class subject_search(delegate.page):
    path = '/search/subjects'

    def GET(self):
        get_results = functools.partial(
            self.get_results, request_label='SUBJECT_SEARCH'
        )
        return render_template('search/subjects', get_results)

    def get_results(
        self,
        q,
        request_label: Literal['SUBJECT_SEARCH', 'SUBJECT_SEARCH_API'],
        offset=0,
        limit=100,
    ):
        response = run_solr_query(
            SubjectSearchScheme(),
            {'q': q},
            offset=offset,
            rows=limit,
            sort='work_count desc',
            request_label=request_label,
        )

        return response


@deprecated("migrated to fastapi")
class subject_search_json(subject_search):
    path = '/search/subjects'
    encoding = 'json'

    def GET(self):
        i = web.input(q='', offset=0, limit=100)
        offset = safeint(i.offset, 0)
        limit = safeint(i.limit, 100)
        limit = min(1000, limit)  # limit limit to 1000.

        response = self.get_results(
            i.q,
            request_label='SUBJECT_SEARCH_API',
            offset=offset,
            limit=limit,
        )

        # Backward compatibility :/
        raw_resp = response.raw_resp['response']
        for doc in raw_resp['docs']:
            doc['type'] = doc.get('subject_type', 'subject')
            doc['count'] = doc.get('work_count', 0)

        web.header('Content-Type', 'application/json')
        return delegate.RawText(json.dumps(raw_resp))


class author_search(delegate.page):
    path = '/search/authors'

    def GET(self):
        get_results = functools.partial(self.get_results, request_label='AUTHOR_SEARCH')
        return render_template('search/authors', get_results)

    def get_results(
        self,
        q,
        request_label: Literal['AUTHOR_SEARCH', 'AUTHOR_SEARCH_API'],
        offset=0,
        limit=100,
        fields='*',
        sort='',
    ):
        resp = run_solr_query(
            AuthorSearchScheme(),
            {'q': q},
            offset=offset,
            rows=limit,
            fields=fields,
            sort=sort,
            request_label=request_label,
        )

        return resp


@deprecated("migrated to fastapi")
class author_search_json(author_search):
    path = '/search/authors'
    encoding = 'json'

    def GET(self):
        i = web.input(q='', offset=0, limit=100, fields='*', sort='')
        offset = safeint(i.offset, 0)
        limit = safeint(i.limit, 100)
        limit = min(1000, limit)  # limit limit to 1000.

        response = self.get_results(
            i.q,
            request_label='AUTHOR_SEARCH_API',
            offset=offset,
            limit=limit,
            fields=i.fields,
            sort=i.sort,
        )
        raw_resp = response.raw_resp['response']
        for doc in raw_resp['docs']:
            # SIGH the public API exposes the key like this :(
            doc['key'] = doc['key'].split('/')[-1]
        web.header('Content-Type', 'application/json')
        return delegate.RawText(json.dumps(raw_resp))


@public
def random_author_search(limit=10) -> SearchResponse:
    return run_solr_query(
        AuthorSearchScheme(),
        {'q': '*:*'},
        rows=limit,
        sort='random.hourly',
    )


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
    from openlibrary.core.lists.model import List

    def cached_get_list_book_keys(key: str, offset: int | None, limit: int | None):
        offset = offset or 0
        limit = limit or 100

        # make cacheable
        if 'env' not in web.ctx:
            delegate.fakeload()
        lst = cast(List, web.ctx.site.get(key))
        return list(itertools.islice(lst.get_work_keys(), offset, offset + limit))

    if list_key_match := re.match(r'^(/people/[^/]+)?/lists/OL\d+L', q):
        # we're making an assumption that q is just a list key
        book_keys = cache.memcache_memoize(
            cached_get_list_book_keys, "search.list_books_query", timeout=5 * 60
        )(list_key_match.group(0), offset, limit)

        # Compose a query for book_keys or fallback special query w/ no results
        q = re.sub(
            r'^(/people/[^/]+)?/lists/OL\d+L',
            f"key:({' OR '.join(book_keys)})" if book_keys else "-key:*",
            q,
        )

        # We've applied the offset to fetching get_list_editions to
        # produce the right set of discrete work IDs. We don't want
        # it applied to paginate our resulting solr query.
        offset = 0
        page = 1
    return q, page, offset, limit


@dataclass(frozen=True)
class PreparedQuery:
    """A container for a query that has been prepared for Solr."""

    query: dict
    page: int
    offset: int
    limit: int


def _process_solr_search_response(response: SearchResponse, fields: str) -> dict:
    """
    Handles the post-processing of the Solr response, which is common
    to both sync and async versions.
    """
    processed_response = response.raw_resp['response']

    if response.highlighting is not None:
        processed_response['highlighting'] = response.highlighting

    # For backward compatibility
    processed_response['num_found'] = processed_response['numFound']

    if fields == '*' or 'availability' in fields:
        docs_for_availability = [
            (
                work['editions']['docs'][0]
                if work.get('editions', {}).get('docs')
                else work
            )
            for work in processed_response.get('docs', [])
        ]
        add_availability(docs_for_availability)

    return processed_response


def _prepare_work_search_query(
    query: dict, page: int, offset: int, limit: int
) -> PreparedQuery:
    """
    Prepares the query by making a deep copy and rewriting list queries,
    returning a structured dataclass.
    """
    # Ensure we don't mutate the `query` passed in by reference
    prepared_query_dict = copy.deepcopy(query)
    prepared_query_dict['wt'] = 'json'

    # Deal with special /lists/ key queries
    q_val, new_page, new_offset, new_limit = rewrite_list_query(
        prepared_query_dict.get('q', ''), page, offset, limit
    )
    prepared_query_dict['q'] = q_val

    return PreparedQuery(
        query=prepared_query_dict,
        page=new_page,
        offset=new_offset,
        limit=new_limit,
    )


# Note: these could share an "implementation" to keep a common interface but it creates a lot more complexity
# Warning: when changing this please also change the async version
@public
def work_search(
    query: dict,
    sort: str | None = None,
    page: int = 1,
    offset: int = 0,
    limit: int = 100,
    fields: str = '*',
    facet: bool = True,
    highlight: bool = False,
    spellcheck_count: int | None = None,
    request_label: SolrRequestLabel = 'UNLABELLED',
) -> dict:
    prepared = _prepare_work_search_query(query, page, offset, limit)

    resp = run_solr_query(
        WorkSearchScheme(),
        prepared.query,
        rows=prepared.limit,
        page=prepared.page,
        sort=sort,
        offset=prepared.offset,
        fields=fields,
        facet=facet,
        highlight=highlight,
        spellcheck_count=spellcheck_count,
        request_label=request_label,
    )

    return _process_solr_search_response(resp, fields)


# Warning: when changing this please also change the sync version
@public
async def work_search_async(
    query: dict,
    sort: str | None = None,
    page: int = 1,
    offset: int = 0,
    limit: int = 100,
    fields: str | list[str] = '*',
    facet: bool = True,
    spellcheck_count: int | None = None,
    request_label: SolrRequestLabel = 'UNLABELLED',
    lang: str | None = None,
) -> dict:
    prepared = _prepare_work_search_query(query, page, offset, limit)
    scheme = WorkSearchScheme(lang=lang)
    resp = await async_run_solr_query(
        scheme,
        prepared.query,
        rows=prepared.limit,
        page=prepared.page,
        sort=sort,
        offset=prepared.offset,
        fields=fields,
        facet=facet,
        spellcheck_count=spellcheck_count,
        request_label=request_label,
    )

    return _process_solr_search_response(resp, fields)


def validate_search_json_query(q: str | None) -> str | None:
    if q and len(q) < 3:
        return 'Query too short, must be at least 3 characters'

    BLOCKED_QUERIES = {'the'}
    if q and q.lower() in BLOCKED_QUERIES:
        return (
            f"Invalid query; the following queries are not allowed: {', '.join(sorted(BLOCKED_QUERIES))}",
        )

    return None


@deprecated("migrated to fastapi")
class search_json(delegate.page):
    path = "/search"
    encoding = "json"

    def GET(self):
        i = web.input(
            author_key=[],
            author_facet=[],
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

        fields = WorkSearchScheme.default_fetched_fields
        if _fields := query.pop('fields', ''):
            fields = _fields.split(',')

        spellcheck_count = safeint(
            query.pop("_spellcheck_count", default_spellcheck_count),
            default=default_spellcheck_count,
        )

        q = query.get('q', '').strip()
        web.header('Content-Type', 'application/json')
        if q_error := validate_search_json_query(q):
            web.ctx.status = '422 Unprocessable Entity'
            return delegate.RawText(json.dumps({'error': q_error}))

        # If the query is a /list/ key, create custom list_editions_query
        query['q'], page, offset, limit = rewrite_list_query(q, page, offset, limit)
        response = work_search(
            query,
            sort=sort,
            page=page,
            offset=offset,
            limit=limit,
            fields=fields,
            # We do not support returning facets from /search.json,
            # so disable it. This makes it much faster.
            facet=False,
            spellcheck_count=spellcheck_count,
            request_label='BOOK_SEARCH_API',
        )
        response['documentation_url'] = "https://openlibrary.org/dev/docs/api/search"
        response['q'] = q
        response['offset'] = offset
        # force all other params to appear before `docs` in json
        docs = response['docs']
        del response['docs']
        response['docs'] = docs
        return delegate.RawText(json.dumps(response, indent=4))


def setup():
    from openlibrary.plugins.worksearch import (
        autocomplete,
        bulk_search,
        languages,
        publishers,
        subjects,
    )

    bulk_search.setup()
    autocomplete.setup()
    subjects.setup()
    publishers.setup()
    languages.setup()


setup()
