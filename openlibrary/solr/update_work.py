from dataclasses import dataclass, field
import datetime
import itertools
import logging
import re
from math import ceil
from statistics import median
from typing import Callable, Literal, Optional, cast, Any
from collections.abc import Iterable

import aiofiles
import httpx
import requests
import sys
import time

from httpx import HTTPError, HTTPStatusError, TimeoutException
from collections import defaultdict

import json
import web

from openlibrary import config
import openlibrary.book_providers as bp
from openlibrary.catalog.utils.query import set_query_host, base_url as get_ol_base_url
from openlibrary.core import helpers as h
from openlibrary.plugins.upstream.utils import safeget
from openlibrary.solr.data_provider import (
    get_data_provider,
    DataProvider,
    ExternalDataProvider,
)
from openlibrary.solr.solr_types import SolrDocument
from openlibrary.solr.update_edition import EditionSolrBuilder, build_edition_data
from openlibrary.utils import uniq
from openlibrary.utils.ddc import normalize_ddc, choose_sorting_ddc
from openlibrary.utils.lcc import short_lcc_to_sortable_lcc, choose_sorting_lcc
from openlibrary.utils.retry import MaxRetriesExceeded, RetryStrategy

logger = logging.getLogger("openlibrary.solr")

re_author_key = re.compile(r'^/(?:a|authors)/(OL\d+A)')
re_bad_char = re.compile('[\x01\x0b\x1a-\x1e]')
re_edition_key = re.compile(r"/books/([^/]+)")
re_solr_field = re.compile(r'^[-\w]+$', re.U)
re_year = re.compile(r'\b(\d{4})\b')

# This will be set to a data provider; have faith, mypy!
data_provider = cast(DataProvider, None)

solr_base_url = None
solr_next: bool | None = None


def get_solr_base_url():
    """
    Get Solr host

    :rtype: str
    """
    global solr_base_url

    load_config()

    if not solr_base_url:
        solr_base_url = config.runtime_config['plugin_worksearch']['solr_base_url']

    return solr_base_url


def set_solr_base_url(solr_url: str):
    global solr_base_url
    solr_base_url = solr_url


def get_solr_next() -> bool:
    """
    Get whether this is the next version of solr; ie new schema configs/fields, etc.
    """
    global solr_next

    if solr_next is None:
        load_config()
        solr_next = config.runtime_config['plugin_worksearch'].get('solr_next', False)

    return solr_next


def set_solr_next(val: bool):
    global solr_next
    solr_next = val


def extract_edition_olid(key: str) -> str:
    m = re_edition_key.match(key)
    if not m:
        raise ValueError(f'Invalid key: {key}')
    return m.group(1)


def get_ia_collection_and_box_id(ia: str) -> Optional['bp.IALiteMetadata']:
    """
    Get the collections and boxids of the provided IA id

    TODO Make the return type of this a namedtuple so that it's easier to reference
    :param str ia: Internet Archive ID
    :return: A dict of the form `{ boxid: set[str], collection: set[str] }`
    :rtype: dict[str, set]
    """
    if len(ia) == 1:
        return None

    def get_list(d, key):
        """
        Return d[key] as some form of list, regardless of if it is or isn't.

        :param dict or None d:
        :param str key:
        :rtype: list
        """
        if not d:
            return []
        value = d.get(key, [])
        if not value:
            return []
        elif value and not isinstance(value, list):
            return [value]
        else:
            return value

    metadata = data_provider.get_metadata(ia)
    if metadata is None:
        # It's none when the IA id is not found/invalid.
        # TODO: It would be better if get_metadata riased an error.
        return None
    return {
        'boxid': set(get_list(metadata, 'boxid')),
        'collection': set(get_list(metadata, 'collection')),
        'access_restricted_item': metadata.get('access-restricted-item'),
    }


class AuthorRedirect(Exception):
    pass


def strip_bad_char(s):
    if not isinstance(s, str):
        return s
    return re_bad_char.sub('', s)


def str_to_key(s):
    """
    Convert a string to a valid Solr field name.
    TODO: this exists in openlibrary/utils/__init__.py str_to_key(), DRY
    :param str s:
    :rtype: str
    """
    to_drop = set(''';/?:@&=+$,<>#%"{}|\\^[]`\n\r''')
    return ''.join(c if c != ' ' else '_' for c in s.lower() if c not in to_drop)


def pick_cover_edition(editions, work_cover_id):
    """
    Get edition that's used as the cover of the work. Otherwise get the first English edition, or otherwise any edition.

    :param list[dict] editions:
    :param int or None work_cover_id:
    :rtype: dict or None
    """
    editions_w_covers = [
        ed
        for ed in editions
        if any(cover_id for cover_id in ed.get('covers', []) if cover_id != -1)
    ]
    return next(
        itertools.chain(
            # Prefer edition with the same cover as the work first
            (ed for ed in editions_w_covers if work_cover_id in ed.get('covers', [])),
            # Then prefer English covers
            (ed for ed in editions_w_covers if 'eng' in str(ed.get('languages', []))),
            # Then prefer anything with a cover
            editions_w_covers,
            # The default: None
            [None],
        )
    )


def pick_number_of_pages_median(editions: list[dict]) -> int | None:
    def to_int(x: Any) -> int | None:
        try:
            return int(x) or None
        except (TypeError, ValueError):  # int(None) -> TypeErr, int("vii") -> ValueErr
            return None

    number_of_pages = [
        pages for e in editions if (pages := to_int(e.get('number_of_pages')))
    ]

    if number_of_pages:
        return ceil(median(number_of_pages))
    else:
        return None


def get_work_subjects(w):
    """
    Gets the subjects of the work grouped by type and then by count.

    :param dict w: Work
    :rtype: dict[str, dict[str, int]]
    :return: Subjects grouped by type, then by subject and count. Example:
    `{ subject: { "some subject": 1 }, person: { "some person": 1 } }`
    """
    assert w['type']['key'] == '/type/work'

    subjects = {}
    field_map = {
        'subjects': 'subject',
        'subject_places': 'place',
        'subject_times': 'time',
        'subject_people': 'person',
    }

    for db_field, solr_field in field_map.items():
        if not w.get(db_field, None):
            continue
        cur = subjects.setdefault(solr_field, {})
        for v in w[db_field]:
            try:
                # TODO Is this still a valid case? Can the subject of a work be an object?
                if isinstance(v, dict):
                    if 'value' not in v:
                        continue
                    v = v['value']
                cur[v] = cur.get(v, 0) + 1
            except:
                logger.error("Failed to process subject: %r", v)
                raise

    return subjects


def four_types(i):
    """
    Moves any subjects not of type subject, time, place, or person into type subject.
    TODO Remove; this is only used after get_work_subjects, which already returns dict with valid keys.

    :param dict[str, dict[str, int]] i: Counts of subjects of the form `{ <subject_type>: { <subject>: <count> }}`
    :return: dict of the same form as the input, but subject_type can only be one of subject, time, place, or person.
    :rtype: dict[str, dict[str, int]]
    """
    want = {'subject', 'time', 'place', 'person'}
    ret = {k: i[k] for k in want if k in i}
    for j in (j for j in i if j not in want):
        for k, v in i[j].items():
            if 'subject' in ret:
                ret['subject'][k] = ret['subject'].get(k, 0) + v
            else:
                ret['subject'] = {k: v}
    return ret


def datetimestr_to_int(datestr):
    """
    Convert an OL datetime to a timestamp integer.

    :param str or dict datestr: Either a string like `"2017-09-02T21:26:46.300245"` or a dict like
        `{"value": "2017-09-02T21:26:46.300245"}`
    :rtype: int
    """
    if isinstance(datestr, dict):
        datestr = datestr['value']

    if datestr:
        try:
            t = h.parse_datetime(datestr)
        except (TypeError, ValueError):
            t = datetime.datetime.utcnow()
    else:
        t = datetime.datetime.utcnow()

    return int(time.mktime(t.timetuple()))


class SolrProcessor:
    """Processes data to into a form suitable for adding to works solr."""

    def __init__(self, resolve_redirects=False):
        self.resolve_redirects = resolve_redirects

    def process_editions(self, w, editions, ia_metadata, identifiers):
        """
        Add extra fields to the editions dicts (ex: pub_year, public_scan, ia_collection, etc.).
        Also gets all the identifiers from the editions and puts them in identifiers.

        :param dict w: Work dict
        :param list[dict] editions: Editions of work
        :param ia_metadata: boxid/collection of each associated IA id
            (ex: `{foobar: {boxid: {"foo"}, collection: {"lendinglibrary"}}}`)
        :param defaultdict[str, list] identifiers: Where to store the identifiers from each edition
        :return: edition dicts with extra fields
        :rtype: list[dict]
        """
        for e in editions:
            pub_year = self.get_pub_year(e)
            if pub_year:
                e['pub_year'] = pub_year

            ia = None
            if 'ocaid' in e:
                ia = e['ocaid']
            elif 'ia_loaded_id' in e:
                loaded = e['ia_loaded_id']
                ia = loaded if isinstance(loaded, str) else loaded[0]

            # If the _ia_meta field is already set in the edition, use it instead of querying archive.org.
            # This is useful to when doing complete reindexing of solr.
            if ia and '_ia_meta' in e:
                ia_meta_fields = e['_ia_meta']
            elif ia:
                ia_meta_fields = ia_metadata.get(ia)
            else:
                ia_meta_fields = None

            if ia_meta_fields:
                collection = ia_meta_fields['collection']
                if 'ia_box_id' in e and isinstance(e['ia_box_id'], str):
                    e['ia_box_id'] = [e['ia_box_id']]
                if ia_meta_fields.get('boxid'):
                    box_id = next(iter(ia_meta_fields['boxid']))
                    e.setdefault('ia_box_id', [])
                    if box_id.lower() not in [x.lower() for x in e['ia_box_id']]:
                        e['ia_box_id'].append(box_id)
                e['ia_collection'] = collection
                e['public_scan'] = ('lendinglibrary' not in collection) and (
                    'printdisabled' not in collection
                )
                e['access_restricted_item'] = ia_meta_fields.get(
                    'access_restricted_item', False
                )

            if 'identifiers' in e:
                for k, id_list in e['identifiers'].items():
                    k_orig = k
                    k = (
                        k.replace('.', '_')
                        .replace(',', '_')
                        .replace('(', '')
                        .replace(')', '')
                        .replace(':', '_')
                        .replace('/', '')
                        .replace('#', '')
                        .lower()
                    )
                    m = re_solr_field.match(k)
                    if not m:
                        logger.error('bad identifier key %s %s', k_orig, k)
                    assert m
                    for v in id_list:
                        v = v.strip()
                        if v not in identifiers[k]:
                            identifiers[k].append(v)
        return sorted(editions, key=lambda e: int(e.get('pub_year') or -sys.maxsize))

    @staticmethod
    def normalize_authors(authors) -> list[dict]:
        """
        Need to normalize to a predictable format because of inconsistencies in data

        >>> SolrProcessor.normalize_authors([
        ...     {'type': {'key': '/type/author_role'}, 'author': '/authors/OL1A'}
        ... ])
        [{'type': {'key': '/type/author_role'}, 'author': {'key': '/authors/OL1A'}}]
        >>> SolrProcessor.normalize_authors([{
        ...     "type": {"key": "/type/author_role"},
        ...     "author": {"key": "/authors/OL1A"}
        ... }])
        [{'type': {'key': '/type/author_role'}, 'author': {'key': '/authors/OL1A'}}]
        """
        return [
            {
                'type': {
                    'key': safeget(lambda: a['type']['key']) or '/type/author_role'
                },
                'author': (
                    a['author']
                    if isinstance(a['author'], dict)
                    else {'key': a['author']}
                ),
            }
            for a in authors
            # TODO: Remove after
            #  https://github.com/internetarchive/openlibrary-client/issues/126
            if 'author' in a
        ]

    async def get_author(self, a):
        """
        Get author dict from author entry in the work.

        get_author({"author": {"key": "/authors/OL1A"}})

        :param dict a: An element of work['authors']
        :return: Full author document
        :rtype: dict or None
        """
        if 'type' in a['author']:
            # means it is already the whole object.
            # It'll be like this when doing re-indexing of solr.
            return a['author']

        key = a['author']['key']
        m = re_author_key.match(key)
        if not m:
            logger.error('invalid author key: %s', key)
            return
        return await data_provider.get_document(key)

    async def extract_authors(self, w):
        """
        Get the full author objects of the given work

        :param dict w:
        :rtype: list[dict]
        """
        authors = [
            await self.get_author(a)
            for a in SolrProcessor.normalize_authors(w.get("authors", []))
        ]

        if any(a['type']['key'] == '/type/redirect' for a in authors):
            if self.resolve_redirects:
                authors = [
                    (
                        await data_provider.get_document(a['location'])
                        if a['type']['key'] == '/type/redirect'
                        else a
                    )
                    for a in authors
                ]
            else:
                # we don't want to raise an exception but just write a warning on the log
                # raise AuthorRedirect
                logger.warning('author redirect error: %s', w['key'])

        # ## Consider only the valid authors instead of raising an error.
        # assert all(a['type']['key'] == '/type/author' for a in authors)
        authors = [a for a in authors if a['type']['key'] == '/type/author']

        return authors

    def get_pub_year(self, e):
        """
        Get the year the given edition was published.

        :param dict e: Full edition dict
        :return: Year edition was published
        :rtype: str or None
        """
        if pub_date := e.get('publish_date', None):
            m = re_year.search(pub_date)
            if m:
                return m.group(1)

    def get_subject_counts(self, w):
        """
        Get the counts of the work's subjects grouped by subject type.

        :param dict w: Work
        :rtype: dict[str, dict[str, int]]
        :return: Subjects grouped by type, then by subject and count. Example:
        `{ subject: { "some subject": 1 }, person: { "some person": 1 } }`
        """
        try:
            subjects = four_types(get_work_subjects(w))
        except:
            logger.error('bad work: %s', w['key'])
            raise

        # FIXME THIS IS ALL DONE IN get_work_subjects! REMOVE
        field_map = {
            'subjects': 'subject',
            'subject_places': 'place',
            'subject_times': 'time',
            'subject_people': 'person',
        }

        for db_field, solr_field in field_map.items():
            if not w.get(db_field, None):
                continue
            cur = subjects.setdefault(solr_field, {})
            for v in w[db_field]:
                try:
                    if isinstance(v, dict):
                        if 'value' not in v:
                            continue
                        v = v['value']
                    cur[v] = cur.get(v, 0) + 1
                except:
                    logger.error("bad subject: %r", v)
                    raise
        # FIXME END_REMOVE

        return subjects

    def build_data(
        self,
        w: dict,
        editions: list[dict],
        ia_metadata: dict[str, Optional['bp.IALiteMetadata']],
    ) -> dict:
        """
        Get the Solr document to insert for the provided work.

        :param w: Work
        """
        d = {}

        def add(name, value):
            if value is not None:
                d[name] = value

        def add_list(name, values):
            d[name] = list(values)

        # use the full key and add type to the doc.
        add('key', w['key'])
        add('type', 'work')
        add('seed', BaseDocBuilder().compute_seeds(w, editions))
        add('title', w.get('title'))
        add('subtitle', w.get('subtitle'))

        add_list("alternative_title", self.get_alternate_titles((w, *editions)))
        add_list('alternative_subtitle', self.get_alternate_subtitles((w, *editions)))

        add('edition_count', len(editions))

        add_list("edition_key", [extract_edition_olid(e['key']) for e in editions])
        add_list(
            "by_statement",
            {e["by_statement"] for e in editions if "by_statement" in e},
        )

        k = 'publish_date'
        pub_dates = {e[k] for e in editions if e.get(k)}
        add_list(k, pub_dates)
        pub_years = {self.get_pub_year(e) for e in editions}
        pub_years = pub_years - {
            None,
        }
        if pub_years:
            add_list('publish_year', pub_years)
            add('first_publish_year', min(int(y) for y in pub_years))

        if number_of_pages_median := pick_number_of_pages_median(editions):
            add('number_of_pages_median', number_of_pages_median)

        add_list(
            "editions",
            [
                build_edition_data(ed, ia_metadata.get(ed.get('ocaid', '').strip()))
                for ed in editions
            ],
        )

        field_map = [
            ('lccn', 'lccn'),
            ('publish_places', 'publish_place'),
            ('oclc_numbers', 'oclc'),
            ('contributions', 'contributor'),
        ]
        for db_key, solr_key in field_map:
            values = {v for e in editions if db_key in e for v in e[db_key]}
            add_list(solr_key, values)

        raw_lccs = {lcc for ed in editions for lcc in ed.get('lc_classifications', [])}
        lccs = {lcc for lcc in map(short_lcc_to_sortable_lcc, raw_lccs) if lcc}
        if lccs:
            add_list("lcc", lccs)
            # Choose the... idk, longest for sorting?
            add("lcc_sort", choose_sorting_lcc(lccs))

        def get_edition_ddcs(ed: dict):
            ddcs: list[str] = ed.get('dewey_decimal_class', [])
            if len(ddcs) > 1:
                # In DDC, `92` or `920` is sometimes appended to a DDC to denote
                # "Biography". We have a clause to handle this if it's part of the same
                # DDC (See utils/ddc.py), but some books have it as an entirely separate
                # DDC; e.g.:
                # * [ "979.4/830046872073", "92" ]
                #   https://openlibrary.org/books/OL3029363M.json
                # * [ "813/.54", "B", "92" ]
                #   https://openlibrary.org/books/OL2401343M.json
                # * [ "092", "823.914" ]
                # https://openlibrary.org/books/OL24767417M
                ddcs = [ddc for ddc in ddcs if ddc not in ('92', '920', '092')]
            return ddcs

        raw_ddcs = {ddc for ed in editions for ddc in get_edition_ddcs(ed)}
        ddcs = {ddc for raw_ddc in raw_ddcs for ddc in normalize_ddc(raw_ddc)}
        if ddcs:
            add_list("ddc", ddcs)
            add("ddc_sort", choose_sorting_ddc(ddcs))

        add_list("isbn", self.get_isbns(editions))
        add("last_modified_i", self.get_last_modified(w, editions))

        d |= self.get_ebook_info(editions, ia_metadata)

        return d

    @staticmethod
    def get_alternate_titles(books: Iterable[dict]) -> set[str]:
        return {
            title
            for bookish in books
            for title in EditionSolrBuilder(bookish).alternative_title
        }

    @staticmethod
    def get_alternate_subtitles(books: Iterable[dict]) -> set[str]:
        """Get subtitles from the editions as alternative titles."""
        return {bookish['subtitle'] for bookish in books if bookish.get('subtitle')}

    def get_isbns(self, editions):
        """
        Get all ISBNs of the given editions. Calculates complementary ISBN13 for each ISBN10 and vice-versa.
        Does not remove '-'s.

        :param list[dict] editions: editions
        :rtype: set[str]
        """
        return {isbn for ed in editions for isbn in EditionSolrBuilder(ed).isbn}

    def get_last_modified(self, work, editions):
        """
        Get timestamp of latest last_modified date between the provided documents.

        :param dict work:
        :param list[dict] editions:
        :rtype: int
        """
        return max(
            datetimestr_to_int(doc.get('last_modified')) for doc in [work] + editions
        )

    @staticmethod
    def get_ebook_info(
        editions: list[dict],
        ia_metadata: dict[str, Optional['bp.IALiteMetadata']],
    ) -> dict:
        """
        Add ebook information from the editions to the work Solr document.
        """
        ebook_info: dict[str, Any] = {}
        ia_provider = cast(
            bp.InternetArchiveProvider, bp.get_book_provider_by_name('ia')
        )

        solr_editions = [
            EditionSolrBuilder(e, ia_metadata.get(e.get('ocaid', '').strip()))
            for e in editions
        ]

        ebook_info["ebook_count_i"] = sum(
            1 for e in solr_editions if e.ebook_access > bp.EbookAccess.UNCLASSIFIED
        )
        ebook_info["ebook_access"] = max(
            (e.ebook_access for e in solr_editions),
            default=bp.EbookAccess.NO_EBOOK,
        ).to_solr_str()
        ebook_info["has_fulltext"] = any(e.has_fulltext for e in solr_editions)
        ebook_info["public_scan_b"] = any(e.public_scan_b for e in solr_editions)

        # IA-specific stuff

        def get_ia_sorting_key(ed: dict) -> tuple[int, str]:
            ocaid = ed['ocaid'].strip()
            access = ia_provider.get_access(ed, ia_metadata.get(ocaid))
            return (
                # -1 to sort in reverse and make public first
                -1 * access.value,
                # De-prioritize google scans because they are lower quality
                '0: non-goog' if not ocaid.endswith('goog') else '1: goog',
            )

        # Store identifiers sorted by most-accessible first.
        ia_eds = sorted((e for e in editions if 'ocaid' in e), key=get_ia_sorting_key)
        ebook_info['ia'] = [e['ocaid'].strip() for e in ia_eds]

        if ia_eds:
            all_collection = sorted(
                uniq(c for e in solr_editions for c in e.ia_collection)
            )
            if all_collection:
                ebook_info['ia_collection'] = all_collection
                # This field is to be deprecated:
                ebook_info['ia_collection_s'] = ';'.join(all_collection)

            # --- These should be deprecated and removed ---
            best_ed = ia_eds[0]
            best_ocaid = best_ed['ocaid'].strip()
            best_access = ia_provider.get_access(best_ed, ia_metadata.get(best_ocaid))
            if best_access > bp.EbookAccess.PRINTDISABLED:
                ebook_info['lending_edition_s'] = extract_edition_olid(best_ed['key'])
                ebook_info['lending_identifier_s'] = best_ed['ocaid']

            printdisabled = [
                extract_edition_olid(ed['key'])
                for ed in ia_eds
                if 'printdisabled' in ed.get('ia_collection', [])
            ]
            if printdisabled:
                ebook_info['printdisabled_s'] = ';'.join(printdisabled)
            # ^^^ These should be deprecated and removed ^^^
        return ebook_info


async def build_data(
    w: dict,
    ia_metadata: dict[str, Optional['bp.IALiteMetadata']] | None = None,
) -> SolrDocument:
    """
    Construct the Solr document to insert into Solr for the given work

    :param w: Work to insert/update
    """
    # Anand - Oct 2013
    # For /works/ia:xxx, editions are already supplied. Querying will empty response.
    if "editions" in w:
        editions = w['editions']
    else:
        editions = data_provider.get_editions_of_work(w)
    authors = await SolrProcessor().extract_authors(w)

    if ia_metadata is None:
        iaids = [e["ocaid"] for e in editions if "ocaid" in e]
        ia_metadata = {iaid: get_ia_collection_and_box_id(iaid) for iaid in iaids}
    return build_data2(w, editions, authors, ia_metadata)


def build_data2(
    w: dict,
    editions: list[dict],
    authors,
    ia: dict[str, Optional['bp.IALiteMetadata']],
) -> SolrDocument:
    """
    Construct the Solr document to insert into Solr for the given work

    :param w: Work to get data for
    :param editions: Editions of work
    :param authors: Authors of work
    :param ia: boxid/collection of each associated IA id
        (ex: `{foobar: {boxid: {"foo"}, collection: {"lendinglibrary"}}}`)
    :rtype: dict
    """
    resolve_redirects = False

    assert w['type']['key'] == '/type/work'
    # Some works are missing a title, but have titles on their editions
    w['title'] = next(
        itertools.chain(
            (
                book['title']
                for book in itertools.chain([w], editions)
                if book.get('title')
            ),
            ['__None__'],
        )
    )
    if w['title'] == '__None__':
        logger.warning('Work missing title %s' % w['key'])

    p = SolrProcessor(resolve_redirects)

    identifiers: dict[str, list] = defaultdict(list)
    editions = p.process_editions(w, editions, ia, identifiers)

    def add_field(doc, name, value):
        doc[name] = value

    def add_field_list(doc, name, field_list):
        doc[name] = list(field_list)

    doc = p.build_data(w, editions, ia)

    # Add ratings info
    doc.update(data_provider.get_work_ratings(w['key']) or {})
    # Add reading log info
    doc.update(data_provider.get_work_reading_log(w['key']) or {})

    work_cover_id = next(
        itertools.chain(
            (cover_id for cover_id in w.get('covers', []) if cover_id != -1), [None]
        )
    )

    cover_edition = pick_cover_edition(editions, work_cover_id)
    if cover_edition:
        m = re_edition_key.match(cover_edition['key'])
        if m:
            cover_edition_key = m.group(1)
            add_field(doc, 'cover_edition_key', cover_edition_key)

    main_cover_id = work_cover_id or (
        next(cover_id for cover_id in cover_edition['covers'] if cover_id != -1)
        if cover_edition
        else None
    )
    if main_cover_id:
        assert isinstance(main_cover_id, int)
        add_field(doc, 'cover_i', main_cover_id)

    k = 'first_sentence'
    fs = {
        e[k]['value'] if isinstance(e[k], dict) else e[k]
        for e in editions
        if e.get(k, None)
    }
    add_field_list(doc, k, fs)

    add_field_list(
        doc,
        'publisher',
        {
            publisher
            for ed in editions
            for publisher in EditionSolrBuilder(ed).publisher
        },
    )

    if get_solr_next():
        add_field_list(
            doc,
            'format',
            {format for ed in editions if (format := EditionSolrBuilder(ed).format)},
        )

    languages: list[str] = []
    ia_loaded_id = set()
    ia_box_id = set()

    for e in editions:
        languages += EditionSolrBuilder(e).languages
        if e.get('ia_loaded_id'):
            if isinstance(e['ia_loaded_id'], str):
                ia_loaded_id.add(e['ia_loaded_id'])
            else:
                try:
                    assert isinstance(e['ia_loaded_id'], list)
                    assert isinstance(e['ia_loaded_id'][0], str)
                except AssertionError:
                    logger.error(
                        "AssertionError: ia=%s, ia_loaded_id=%s",
                        e.get("ia"),
                        e['ia_loaded_id'],
                    )
                    raise
                ia_loaded_id.update(e['ia_loaded_id'])
        if e.get('ia_box_id'):
            if isinstance(e['ia_box_id'], str):
                ia_box_id.add(e['ia_box_id'])
            else:
                try:
                    assert isinstance(e['ia_box_id'], list)
                    assert isinstance(e['ia_box_id'][0], str)
                except AssertionError:
                    logger.error("AssertionError: %s", e['key'])
                    raise
                ia_box_id.update(e['ia_box_id'])
    if languages:
        add_field_list(doc, 'language', uniq(languages))

    # if lending_edition or in_library_edition:
    #    add_field(doc, "borrowed_b", is_borrowed(lending_edition or in_library_edition))

    author_keys = [
        m.group(1) for m in (re_author_key.match(a['key']) for a in authors) if m
    ]
    author_names = [a.get('name', '') for a in authors]
    add_field_list(doc, 'author_key', author_keys)
    add_field_list(doc, 'author_name', author_names)

    alt_names = set()
    for a in authors:
        if 'alternate_names' in a:
            alt_names.update(a['alternate_names'])

    add_field_list(doc, 'author_alternative_name', alt_names)
    add_field_list(
        doc, 'author_facet', (' '.join(v) for v in zip(author_keys, author_names))
    )

    subjects = p.get_subject_counts(w)
    # if subjects:
    #    add_field(doc, 'fiction', subjects['fiction'])
    for k in 'person', 'place', 'subject', 'time':
        if k not in subjects:
            continue
        subjects_k_keys = list(subjects[k])
        add_field_list(doc, k, subjects_k_keys)
        add_field_list(doc, k + '_facet', subjects_k_keys)
        subject_keys = [str_to_key(s) for s in subjects_k_keys]
        add_field_list(doc, k + '_key', subject_keys)

    for k in sorted(identifiers):
        add_field_list(doc, 'id_' + k, identifiers[k])

    if ia_loaded_id:
        add_field_list(doc, 'ia_loaded_id', ia_loaded_id)

    if ia_box_id:
        add_field_list(doc, 'ia_box_id', ia_box_id)

    return cast(SolrDocument, doc)


async def solr_insert_documents(
    documents: list[dict],
    solr_base_url: str | None = None,
    skip_id_check=False,
):
    """
    Note: This has only been tested with Solr 8, but might work with Solr 3 as well.
    """
    solr_base_url = solr_base_url or get_solr_base_url()
    params = {}
    if skip_id_check:
        params['overwrite'] = 'false'
    logger.debug(f"POSTing update to {solr_base_url}/update {params}")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f'{solr_base_url}/update',
            timeout=30,  # seconds; the default timeout is silly short
            params=params,
            headers={'Content-Type': 'application/json'},
            content=json.dumps(documents),
        )
    resp.raise_for_status()


def listify(f):
    """Decorator to transform a generator function into a function
    returning list of values.
    """

    def g(*a, **kw):
        return list(f(*a, **kw))

    return g


class BaseDocBuilder:
    re_subject = re.compile("[, _]+")

    @listify
    def compute_seeds(self, work, editions, authors=None):
        """
        Compute seeds from given work, editions, and authors.

        :param dict work:
        :param list[dict] editions:
        :param list[dict] or None authors: If not provided taken from work.
        :rtype: list[str]
        """

        for e in editions:
            yield e['key']

        if work:
            yield work['key']
            yield from self.get_subject_seeds(work)

            if authors is None:
                authors = [
                    a['author']
                    for a in work.get("authors", [])
                    if 'author' in a and 'key' in a['author']
                ]

        if authors:
            for a in authors:
                yield a['key']

    def get_subject_seeds(self, work):
        """Yields all subject seeds from the work."""
        return (
            self._prepare_subject_keys("/subjects/", work.get("subjects"))
            + self._prepare_subject_keys(
                "/subjects/person:", work.get("subject_people")
            )
            + self._prepare_subject_keys("/subjects/place:", work.get("subject_places"))
            + self._prepare_subject_keys("/subjects/time:", work.get("subject_times"))
        )

    def _prepare_subject_keys(self, prefix, subject_names):
        subject_names = subject_names or []
        return [self.get_subject_key(prefix, s) for s in subject_names]

    def get_subject_key(self, prefix, subject):
        if isinstance(subject, str):
            key = prefix + self.re_subject.sub("_", subject.lower()).strip("_")
            return key


def solr_update(
    update_request: 'SolrUpdateState',
    skip_id_check=False,
    solr_base_url: str | None = None,
) -> None:
    content = update_request.to_solr_requests_json()

    solr_base_url = solr_base_url or get_solr_base_url()
    params = {
        # Don't fail the whole batch if one bad apple
        'update.chain': 'tolerant-chain'
    }
    if skip_id_check:
        params['overwrite'] = 'false'

    def make_request():
        logger.debug(f"POSTing update to {solr_base_url}/update {params}")
        try:
            resp = httpx.post(
                f'{solr_base_url}/update',
                # Large batches especially can take a decent chunk of time
                timeout=300,
                params=params,
                headers={'Content-Type': 'application/json'},
                content=content,
            )

            if resp.status_code == 400:
                resp_json = resp.json()

                indiv_errors = resp_json.get('responseHeader', {}).get('errors', [])
                if indiv_errors:
                    for e in indiv_errors:
                        logger.error(f'Individual Solr POST Error: {e}')

                global_error = resp_json.get('error')
                if global_error:
                    logger.error(f'Global Solr POST Error: {global_error.get("msg")}')

                if not (indiv_errors or global_error):
                    # We can handle the above errors. Any other 400 status codes
                    # are fatal and should cause a retry
                    resp.raise_for_status()
            else:
                resp.raise_for_status()
        except HTTPStatusError as e:
            logger.error(f'HTTP Status Solr POST Error: {e}')
            raise
        except TimeoutException:
            logger.error(f'Timeout Solr POST Error: {content}')
            raise
        except HTTPError as e:
            logger.error(f'HTTP Solr POST Error: {e}')
            raise

    retry = RetryStrategy(
        [HTTPStatusError, TimeoutException, HTTPError],
        max_retries=5,
        delay=8,
    )

    try:
        return retry(make_request)
    except MaxRetriesExceeded as e:
        logger.error(f'Max retries exceeded for Solr POST: {e.last_exception}')


def get_subject(key):
    subject_key = key.split("/")[-1]

    if ":" in subject_key:
        subject_type, subject_key = subject_key.split(":", 1)
    else:
        subject_type = "subject"

    search_field = "%s_key" % subject_type
    facet_field = "%s_facet" % subject_type

    # Handle upper case or any special characters that may be present
    subject_key = str_to_key(subject_key)
    key = f"/subjects/{subject_type}:{subject_key}"

    result = requests.get(
        f'{get_solr_base_url()}/select',
        params={
            'wt': 'json',
            'json.nl': 'arrarr',
            'q': f'{search_field}:{subject_key}',
            'rows': 0,
            'facet': 'true',
            'facet.field': facet_field,
            'facet.mincount': 1,
            'facet.limit': 100,
        },
    ).json()

    work_count = result['response']['numFound']
    facets = result['facet_counts']['facet_fields'].get(facet_field, [])

    names = [name for name, count in facets if str_to_key(name) == subject_key]

    if names:
        name = names[0]
    else:
        name = subject_key.replace("_", " ")

    return {
        "key": key,
        "type": "subject",
        "subject_type": subject_type,
        "name": name,
        "work_count": work_count,
    }


def subject_name_to_key(
    subject_type: Literal['subject', 'person', 'place', 'time'], subject_name: str
) -> str:
    escaped_subject_name = str_to_key(subject_name)
    if subject_type == 'subject':
        return f"/subjects/{escaped_subject_name}"
    else:
        return f"/subjects/{subject_type}:{escaped_subject_name}"


def build_subject_doc(
    subject_type: Literal['subject', 'person', 'place', 'time'],
    subject_name: str,
    work_count: int,
):
    """Build the `type:subject` solr doc for this subject."""
    return {
        'key': subject_name_to_key(subject_type, subject_name),
        'name': subject_name,
        'type': 'subject',
        'subject_type': subject_type,
        'work_count': work_count,
    }


async def update_author(a: dict) -> 'SolrUpdateState':
    """
    Get the Solr requests necessary to insert/update/delete an Author in Solr.
    :param dict a: Author
    """
    author_id = a['key'].split("/")[-1]
    facet_fields = ['subject', 'time', 'person', 'place']
    base_url = get_solr_base_url() + '/select'

    async with httpx.AsyncClient() as client:
        response = await client.get(
            base_url,
            params=[  # type: ignore[arg-type]
                ('wt', 'json'),
                ('json.nl', 'arrarr'),
                ('q', 'author_key:%s' % author_id),
                ('sort', 'edition_count desc'),
                ('rows', 1),
                ('fl', 'title,subtitle'),
                ('facet', 'true'),
                ('facet.mincount', 1),
            ]
            + [('facet.field', '%s_facet' % field) for field in facet_fields],
        )
        reply = response.json()
    work_count = reply['response']['numFound']
    docs = reply['response'].get('docs', [])
    top_work = None
    if docs and docs[0].get('title', None):
        top_work = docs[0]['title']
        if docs[0].get('subtitle', None):
            top_work += ': ' + docs[0]['subtitle']
    all_subjects = []
    for f in facet_fields:
        for s, num in reply['facet_counts']['facet_fields'][f + '_facet']:
            all_subjects.append((num, s))
    all_subjects.sort(reverse=True)
    top_subjects = [s for num, s in all_subjects[:10]]
    d = cast(
        SolrDocument,
        {
            'key': f'/authors/{author_id}',
            'type': 'author',
        },
    )

    if a.get('name', None):
        d['name'] = a['name']

    alternate_names = a.get('alternate_names', [])
    if alternate_names:
        d['alternate_names'] = alternate_names

    if a.get('birth_date', None):
        d['birth_date'] = a['birth_date']
    if a.get('death_date', None):
        d['death_date'] = a['death_date']
    if a.get('date', None):
        d['date'] = a['date']

    if top_work:
        d['top_work'] = top_work
    d['work_count'] = work_count
    d['top_subjects'] = top_subjects

    return SolrUpdateState(adds=[d])


re_edition_key_basename = re.compile("^[a-zA-Z0-9:.-]+$")


def solr_select_work(edition_key):
    """
    Get corresponding work key for given edition key in Solr.

    :param str edition_key: (ex: /books/OL1M)
    :return: work_key
    :rtype: str or None
    """
    # solr only uses the last part as edition_key
    edition_key = edition_key.split("/")[-1]

    if not re_edition_key_basename.match(edition_key):
        return None

    edition_key = solr_escape(edition_key)
    reply = requests.get(
        f'{get_solr_base_url()}/select',
        params={
            'wt': 'json',
            'q': f'edition_key:{edition_key}',
            'rows': 1,
            'fl': 'key',
        },
    ).json()
    if docs := reply['response'].get('docs', []):
        return docs[0]['key']  # /works/ prefix is in solr


@dataclass
class SolrUpdateState:
    keys: list[str] = field(default_factory=list)
    """Keys to update"""

    adds: list[SolrDocument] = field(default_factory=list)
    """Records to be added/modified"""

    deletes: list[str] = field(default_factory=list)
    """Records to be deleted"""

    commit: bool = False

    # Override the + operator
    def __add__(self, other):
        if isinstance(other, SolrUpdateState):
            return SolrUpdateState(
                adds=self.adds + other.adds,
                deletes=self.deletes + other.deletes,
                keys=self.keys + other.keys,
                commit=self.commit or other.commit,
            )
        else:
            raise TypeError(f"Cannot add {type(self)} and {type(other)}")

    def has_changes(self) -> bool:
        return bool(self.adds or self.deletes)

    def to_solr_requests_json(self, indent: str | None = None, sep=',') -> str:
        result = '{'
        if self.deletes:
            result += f'"delete": {json.dumps(self.deletes, indent=indent)}' + sep
        for doc in self.adds:
            result += f'"add": {json.dumps({"doc": doc}, indent=indent)}' + sep
        if self.commit:
            result += '"commit": {}' + sep

        if result.endswith(sep):
            result = result[: -len(sep)]
        result += '}'
        return result

    def clear_requests(self) -> None:
        self.adds.clear()
        self.deletes.clear()


class AbstractSolrUpdater:
    key_prefix: str
    thing_type: str

    def key_test(self, key: str) -> bool:
        return key.startswith(self.key_prefix)

    async def preload_keys(self, keys: Iterable[str]):
        await data_provider.preload_documents(keys)

    async def update_key(self, thing: dict) -> SolrUpdateState:
        raise NotImplementedError()


class EditionSolrUpdater(AbstractSolrUpdater):
    key_prefix = '/books/'
    thing_type = '/type/edition'

    async def update_key(self, thing: dict) -> SolrUpdateState:
        update = SolrUpdateState()
        if thing['type']['key'] == self.thing_type:
            if thing.get("works"):
                update.keys.append(thing["works"][0]['key'])
                # Make sure we remove any fake works created from orphaned editions
                update.keys.append(thing['key'].replace('/books/', '/works/'))
            else:
                # index the edition as it does not belong to any work
                update.keys.append(thing['key'].replace('/books/', '/works/'))
        else:
            logger.info(
                "%r is a document of type %r. Checking if any work has it as edition in solr...",
                thing['key'],
                thing['type']['key'],
            )
            work_key = solr_select_work(thing['key'])
            if work_key:
                logger.info("found %r, updating it...", work_key)
                update.keys.append(work_key)
        return update


class WorkSolrUpdater(AbstractSolrUpdater):
    key_prefix = '/works/'
    thing_type = '/type/work'

    async def preload_keys(self, keys: Iterable[str]):
        await super().preload_keys(keys)
        data_provider.preload_editions_of_works(keys)

    async def update_key(self, work: dict) -> SolrUpdateState:
        """
        Get the Solr requests necessary to insert/update this work into Solr.

        :param dict work: Work to insert/update
        """
        wkey = work['key']
        update = SolrUpdateState()

        # q = {'type': '/type/redirect', 'location': wkey}
        # redirect_keys = [r['key'][7:] for r in query_iter(q)]
        # redirect_keys = [k[7:] for k in data_provider.find_redirects(wkey)]

        # deletes += redirect_keys
        # deletes += [wkey[7:]] # strip /works/ from /works/OL1234W

        # Handle edition records as well
        # When an edition does not contain a works list, create a fake work and index it.
        if work['type']['key'] == '/type/edition':
            fake_work = {
                # Solr uses type-prefixed keys. It's required to be unique across
                # all types of documents. The website takes care of redirecting
                # /works/OL1M to /books/OL1M.
                'key': wkey.replace("/books/", "/works/"),
                'type': {'key': '/type/work'},
                'title': work.get('title'),
                'editions': [work],
                'authors': [
                    {'type': '/type/author_role', 'author': {'key': a['key']}}
                    for a in work.get('authors', [])
                ],
            }
            # Hack to add subjects when indexing /books/ia:xxx
            if work.get("subjects"):
                fake_work['subjects'] = work['subjects']
            return await self.update_key(fake_work)
        elif work['type']['key'] == '/type/work':
            try:
                solr_doc = await build_data(work)
            except:
                logger.error("failed to update work %s", work['key'], exc_info=True)
            else:
                if solr_doc is not None:
                    iaids = solr_doc.get('ia') or []
                    # Delete all ia:foobar keys
                    if iaids:
                        update.deletes += [f"/works/ia:{iaid}" for iaid in iaids]
                    update.adds.append(solr_doc)
        else:
            logger.error("unrecognized type while updating work %s", wkey)

        return update


class AuthorSolrUpdater(AbstractSolrUpdater):
    key_prefix = '/authors/'
    thing_type = '/type/author'

    def update_key(self, thing: dict) -> SolrUpdateState:
        return update_author(thing)


SOLR_UPDATERS: list[AbstractSolrUpdater] = [
    # ORDER MATTERS
    EditionSolrUpdater(),
    WorkSolrUpdater(),
    AuthorSolrUpdater(),
]


async def update_keys(
    keys: list[str],
    commit=True,
    output_file=None,
    skip_id_check=False,
    update: Literal['update', 'print', 'pprint', 'quiet'] = 'update',
) -> 'SolrUpdateState':
    """
    Insert/update the documents with the provided keys in Solr.

    :param list[str] keys: Keys to update (ex: ["/books/OL1M"]).
    :param bool commit: Create <commit> tags to make Solr persist the changes (and make the public/searchable).
    :param str output_file: If specified, will save all update actions to output_file **instead** of sending to Solr.
        Each line will be JSON object.
        FIXME Updates to editions/subjects ignore output_file and will be sent (only) to Solr regardless.
    """
    logger.debug("BEGIN update_keys")

    def _solr_update(update_state: 'SolrUpdateState'):
        if update == 'update':
            return solr_update(update_state, skip_id_check)
        elif update == 'pprint':
            print(update_state.to_solr_requests_json(sep='\n', indent=4))
        elif update == 'print':
            print(update_state.to_solr_requests_json(sep='\n'))
        elif update == 'quiet':
            pass

    global data_provider
    if data_provider is None:
        data_provider = get_data_provider('default')

    net_update = SolrUpdateState(keys=keys, commit=commit)

    for updater in SOLR_UPDATERS:
        update_state = SolrUpdateState(commit=commit)
        updater_keys = uniq(k for k in net_update.keys if updater.key_test(k))
        await updater.preload_keys(updater_keys)
        for key in updater_keys:
            logger.debug(f"processing {key}")
            try:
                thing = await data_provider.get_document(key)

                if thing and thing['type']['key'] == '/type/redirect':
                    logger.warning("Found redirect to %r", thing['location'])
                    # When the given key is not found or redirects to another thing,
                    # explicitly delete the key. It won't get deleted otherwise.
                    update_state.deletes.append(thing['key'])
                    thing = await data_provider.get_document(thing['location'])

                if not thing:
                    logger.warning("No thing found for key %r. Ignoring...", key)
                    continue
                if thing['type']['key'] == '/type/delete':
                    logger.info(
                        "Found a document of type %r. queuing for deleting it solr..",
                        thing['type']['key'],
                    )
                    update_state.deletes.append(thing['key'])
                else:
                    update_state += await updater.update_key(thing)
            except:
                logger.error("Failed to update %r", key, exc_info=True)

        if update_state.has_changes():
            if output_file:
                async with aiofiles.open(output_file, "w") as f:
                    for doc in update_state.adds:
                        await f.write(f"{json.dumps(doc)}\n")
            else:
                _solr_update(update_state)
        net_update += update_state

    logger.debug("END update_keys")
    return net_update


def solr_escape(query):
    """
    Escape special characters in Solr query.

    :param str query:
    :rtype: str
    """
    return re.sub(r'([\s\-+!()|&{}\[\]^"~*?:\\])', r'\\\1', query)


async def do_updates(keys):
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    await update_keys(keys, commit=False)


def load_config(c_config='conf/openlibrary.yml'):
    if not config.runtime_config:
        config.load(c_config)
        config.load_config(c_config)


def load_configs(
    c_host: str,
    c_config: str,
    c_data_provider: (
        DataProvider | Literal["default", "legacy", "external"]
    ) = 'default',
) -> DataProvider:
    host = web.lstrips(c_host, "http://").strip("/")
    set_query_host(host)

    load_config(c_config)

    global data_provider
    if data_provider is None:
        if isinstance(c_data_provider, DataProvider):
            data_provider = c_data_provider
        elif c_data_provider == 'external':
            data_provider = ExternalDataProvider(host)
        else:
            data_provider = get_data_provider(c_data_provider)
    return data_provider


async def main(
    keys: list[str],
    ol_url="http://openlibrary.org",
    ol_config="openlibrary.yml",
    output_file: str | None = None,
    commit=True,
    data_provider: Literal['default', 'legacy', 'external'] = "default",
    solr_base: str | None = None,
    solr_next=False,
    update: Literal['update', 'print', 'pprint'] = 'update',
):
    """
    Insert the documents with the given keys into Solr.

    :param keys: The keys of the items to update (ex: /books/OL1M)
    :param ol_url: URL of the openlibrary website
    :param ol_config: Open Library config file
    :param output_file: Where to save output
    :param commit: Whether to also trigger a Solr commit
    :param data_provider: Name of the data provider to use
    :param solr_base: If wanting to override openlibrary.yml
    :param solr_next: Whether to assume schema of next solr version is active
    :param update: Whether/how to do the actual solr update call
    """
    load_configs(ol_url, ol_config, data_provider)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    if keys[0].startswith('//'):
        keys = [k[1:] for k in keys]

    if solr_base:
        set_solr_base_url(solr_base)

    set_solr_next(solr_next)

    await update_keys(keys, commit=commit, output_file=output_file, update=update)


if __name__ == '__main__':
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(main).run()
