from __future__ import print_function
import datetime
import itertools
import logging
import os
import re
from typing import Literal, List, Union

import httpx
import requests
import sys
import time

from httpx import HTTPError
from six.moves.urllib.parse import urlparse
from collections import defaultdict
from unicodedata import normalize

import json
import six
from six.moves.http_client import HTTPConnection
import web
from lxml.etree import tostring, Element, SubElement

from infogami.infobase.client import ClientException
from openlibrary import config
from openlibrary.catalog.utils.query import set_query_host, base_url as get_ol_base_url
from openlibrary.core import helpers as h
from openlibrary.core import ia
from openlibrary.plugins.upstream.utils import url_quote
from openlibrary.solr.data_provider import get_data_provider, DataProvider
from openlibrary.utils.ddc import normalize_ddc, choose_sorting_ddc
from openlibrary.utils.isbn import opposite_isbn
from openlibrary.utils.lcc import short_lcc_to_sortable_lcc, choose_sorting_lcc

logger = logging.getLogger("openlibrary.solr")

re_lang_key = re.compile(r'^/(?:l|languages)/([a-z]{3})$')
re_author_key = re.compile(r'^/(?:a|authors)/(OL\d+A)')
re_bad_char = re.compile('[\x01\x0b\x1a-\x1e]')
re_edition_key = re.compile(r"/books/([^/]+)")
re_iso_date = re.compile(r'^(\d{4})-\d\d-\d\d$')
re_solr_field = re.compile(r'^[-\w]+$', re.U)
re_year = re.compile(r'(\d{4})$')

data_provider = None
_ia_db = None

solr_base_url = None


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


def get_ia_collection_and_box_id(ia):
    """
    Get the collections and boxids of the provided IA id

    TODO Make the return type of this a namedtuple so that it's easier to reference
    :param str ia: Internet Archive ID
    :return: A dict of the form `{ boxid: set[str], collection: set[str] }`
    :rtype: dict[str, set]
    """
    if len(ia) == 1:
        return

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
    return {
        'boxid': set(get_list(metadata, 'boxid')),
        'collection': set(get_list(metadata, 'collection'))
    }

class AuthorRedirect (Exception):
    pass

def strip_bad_char(s):
    if not isinstance(s, six.string_types):
        return s
    return re_bad_char.sub('', s)

def add_field(doc, name, value):
    """
    Add an XML element to the provided doc of the form `<field name="$name">$value</field>`.

    Example:

    >>> tostring(add_field(Element("doc"), "foo", "bar"))
    "<doc><field name="foo">bar</field></doc>"

    :param lxml.etree.ElementBase doc: Parent document to append to.
    :param str name:
    :param value:
    """
    field = Element("field", name=name)
    try:
        field.text = normalize('NFC', six.text_type(strip_bad_char(value)))
    except:
        logger.error('Error in normalizing %r', value)
        raise
    doc.append(field)

def add_field_list(doc, name, field_list):
    """
    Add multiple XML elements to the provided element of the form `<field name="$name">$value[i]</field>`.

    Example:

    >>> tostring(add_field_list(Element("doc"), "foo", [1,2]))
    "<doc><field name="foo">1</field><field name="foo">2</field></doc>"

    :param lxml.etree.ElementBase doc: Parent document to append to.
    :param str name:
    :param list field_list:
    """
    for value in field_list:
        add_field(doc, name, value)

def str_to_key(s):
    """
    Convert a string to a valid Solr field name.
    TODO: this exists in openlibrary/utils/__init__.py str_to_key(), DRY
    :param str s:
    :rtype: str
    """
    to_drop = set(''';/?:@&=+$,<>#%"{}|\\^[]`\n\r''')
    return ''.join(c if c != ' ' else '_' for c in s.lower() if c not in to_drop)

re_not_az = re.compile('[^a-zA-Z]')
def is_sine_nomine(pub):
    """
    Check if the publisher is 'sn' (excluding non-letter characters).

    :param str pub:
    :rtype: bool
    """
    return re_not_az.sub('', pub).lower() == 'sn'


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
    return next(itertools.chain(
        # Prefer edition with the same cover as the work first
        (ed for ed in editions_w_covers if work_cover_id in ed.get('covers', [])),
        # Then prefer English covers
        (ed for ed in editions_w_covers if 'eng' in str(ed.get('languages', []))),
        # Then prefer anything with a cover
        editions_w_covers,
        # The default: None
        [None],
    ))


def get_work_subjects(w):
    """
    Get's the subjects of the work grouped by type and then by count.

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
    ret = dict((k, i[k]) for k in want if k in i)
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


def safeget(func):
    """
    TODO: DRY with solrbuilder copy
    >>> safeget(lambda: {}['foo'])
    >>> safeget(lambda: {}['foo']['bar'][0])
    >>> safeget(lambda: {'foo': []}['foo'][0])
    >>> safeget(lambda: {'foo': {'bar': [42]}}['foo']['bar'][0])
    42
    >>> safeget(lambda: {'foo': 'blah'}['foo']['bar'])
    """
    try:
        return func()
    except (KeyError, IndexError, TypeError):
        return None


class SolrProcessor:
    """Processes data to into a form suitable for adding to works solr.
    """
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
                ia = loaded if isinstance(loaded, six.string_types) else loaded[0]

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
                if 'ia_box_id' in e and isinstance(e['ia_box_id'], six.string_types):
                    e['ia_box_id'] = [e['ia_box_id']]
                if ia_meta_fields.get('boxid'):
                    box_id = list(ia_meta_fields['boxid'])[0]
                    e.setdefault('ia_box_id', [])
                    if box_id.lower() not in [x.lower() for x in e['ia_box_id']]:
                        e['ia_box_id'].append(box_id)
                e['ia_collection'] = collection
                e['public_scan'] = ('lendinglibrary' not in collection) and ('printdisabled' not in collection)

            if 'identifiers' in e:
                for k, id_list in e['identifiers'].items():
                    k_orig = k
                    k = k.replace('.', '_').replace(',', '_').replace('(', '').replace(')', '').replace(':', '_').replace('/', '').replace('#', '').lower()
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
    def normalize_authors(authors) -> List[dict]:
        """
        Need to normalize to a predictable format because of inconsitencies in data

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
                    a['author'] if isinstance(a['author'], dict)
                    else {'key': a['author']}
                )
            }
            for a in authors
            # TODO: Remove after
            #  https://github.com/internetarchive/openlibrary-client/issues/126
            if 'author' in a
        ]

    def get_author(self, a):
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
        return data_provider.get_document(key)

    def extract_authors(self, w):
        """
        Get the full author objects of the given work

        :param dict w:
        :rtype: list[dict]
        """
        authors = [
            self.get_author(a)
            for a in SolrProcessor.normalize_authors(w.get("authors", []))
        ]

        if any(a['type']['key'] == '/type/redirect' for a in authors):
            if self.resolve_redirects:
                def resolve(a):
                    if a['type']['key'] == '/type/redirect':
                        a = data_provider.get_document(a['location'])
                    return a
                authors = [resolve(a) for a in authors]
            else:
                # we don't want to raise an exception but just write a warning on the log
                # raise AuthorRedirect
                logger.warning('author redirect error: %s', w['key'])

        ## Consider only the valid authors instead of raising an error.
        #assert all(a['type']['key'] == '/type/author' for a in authors)
        authors = [a for a in authors if a['type']['key'] == '/type/author']

        return authors

    def get_pub_year(self, e):
        """
        Get the year the given edition was published.

        :param dict e: Full edition dict
        :return: Year edition was published
        :rtype: str or None
        """
        pub_date = e.get('publish_date', None)
        if pub_date:
            m = re_iso_date.match(pub_date)
            if m:
                return m.group(1)
            m = re_year.search(pub_date)
            if m:
                return m.group(1)

    def get_subject_counts(self, w, editions, has_fulltext):
        """
        Get the counts of the work's subjects grouped by subject type.
        Also includes subjects like "Accessible book" or "Protected DAISY" based on editions.

        :param dict w: Work
        :param list[dict] editions: Editions of Work
        :param bool has_fulltext: Whether this work has a copy on IA
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

        # TODO This literally *exactly* how has_fulltext is calculated
        if any(e.get('ocaid', None) for e in editions):
            subjects.setdefault('subject', {})
            subjects['subject']['Accessible book'] = subjects['subject'].get('Accessible book', 0) + 1
            if not has_fulltext:
                subjects['subject']['Protected DAISY'] = subjects['subject'].get('Protected DAISY', 0) + 1
        return subjects

    def build_data(self, w, editions, subjects, has_fulltext):
        """
        Get the Solr document to insert for the provided work.

        :param dict w: Work
        :param list[dict] editions: Editions of work
        :param dict[str, dict[str, int]] subjects: subject counts grouped by subject_type
        :param bool has_fulltext:
        :rtype: dict
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
        add('has_fulltext', has_fulltext)

        add_list("alternative_title", self.get_alternate_titles(w, editions))
        add_list('alternative_subtitle', self.get_alternate_subtitles(w, editions))

        add('edition_count', len(editions))

        add_list("edition_key", [re_edition_key.match(e['key']).group(1) for e in editions])
        add_list("by_statement", set(e["by_statement"] for e in editions if "by_statement" in e))

        k = 'publish_date'
        pub_dates = set(e[k] for e in editions if e.get(k))
        add_list(k, pub_dates)
        pub_years = set(m.group(1) for m in (re_year.search(date) for date in pub_dates) if m)
        if pub_years:
            add_list('publish_year', pub_years)
            add('first_publish_year', min(int(y) for y in pub_years))

        field_map = [
            ('lccn', 'lccn'),
            ('publish_places', 'publish_place'),
            ('oclc_numbers', 'oclc'),
            ('contributions', 'contributor'),
        ]
        for db_key, solr_key in field_map:
            values = set(v for e in editions
                           if db_key in e
                           for v in e[db_key])
            add_list(solr_key, values)

        raw_lccs = set(lcc
                       for ed in editions
                       for lcc in ed.get('lc_classifications', []))
        lccs = set(lcc for lcc in map(short_lcc_to_sortable_lcc, raw_lccs) if lcc)
        if lccs:
            add_list("lcc", lccs)
            # Choose the... idk, longest for sorting?
            add("lcc_sort", choose_sorting_lcc(lccs))

        def get_edition_ddcs(ed: dict):
            ddcs = ed.get('dewey_decimal_class', [])  # type: List[str]
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

        raw_ddcs = set(ddc
                       for ed in editions
                       for ddc in get_edition_ddcs(ed))
        ddcs = set(ddc
                   for raw_ddc in raw_ddcs
                   for ddc in normalize_ddc(raw_ddc))
        if ddcs:
            add_list("ddc", ddcs)
            add("ddc_sort", choose_sorting_ddc(ddcs))

        add_list("isbn", self.get_isbns(editions))
        add("last_modified_i", self.get_last_modified(w, editions))

        self.add_ebook_info(d, editions)

        # Anand - Oct 2013
        # If not public scan then add the work to Protected DAISY subject.
        # This is not the right place to add it, but seems to the quickest way.
        if has_fulltext and not d.get('public_scan_b'):
            subjects['subject']['Protected DAISY'] = 1

        return d

    def get_alternate_titles(self, w, editions):
        """
        Get titles from the editions as alternative titles.

        :param dict w:
        :param list[dict] editions:
        :rtype: set[str]
        """
        result = set()
        for e in editions:
            result.add(e.get('title'))
            result.update(e.get('work_titles', []))
            result.update(e.get('other_titles', []))

        # Remove original title and None.
        # None would've got in if any of the editions has no title.
        result.discard(None)
        result.discard(w.get('title'))
        return result

    def get_alternate_subtitles(self, w, editions):
        """
        Get subtitles from the editions as alternative titles.

        :param dict w:
        :param list[dict] editions:
        :rtype: set[str]
        """
        subtitle = w.get('subtitle')
        return set(e['subtitle'] for e in editions if e.get('subtitle') and e['subtitle'] != subtitle)

    def get_isbns(self, editions):
        """
        Get all ISBNs of the given editions. Calculates complementary ISBN13 for each ISBN10 and vice-versa.
        Does not remove '-'s.

        :param list[dict] editions: editions
        :rtype: set[str]
        """
        isbns = set()

        isbns.update(v.replace("_", "").strip() for e in editions for v in e.get("isbn_10", []))
        isbns.update(v.replace("_", "").strip() for e in editions for v in e.get("isbn_13", []))

        # Get the isbn13 when isbn10 is present and vice-versa.
        alt_isbns = [opposite_isbn(v) for v in isbns]
        isbns.update(v for v in alt_isbns if v is not None)

        return isbns

    def get_last_modified(self, work, editions):
        """
        Get timestamp of latest last_modified date between the provided documents.

        :param dict work:
        :param list[dict] editions:
        :rtype: int
        """
        return max(datetimestr_to_int(doc.get('last_modified')) for doc in [work] + editions)

    def add_ebook_info(self, doc, editions):
        """
        Add ebook information from the editions to the work Solr document.

        :param dict doc: Solr document for the work these editions belong to.
        :param list[dict] editions: Editions with extra data from process_editions
        """
        def add(name, value):
            if value is not None:
                doc[name] = value

        def add_list(name, values):
            doc[name] = list(values)

        pub_goog = set() # google
        pub_nongoog = set()
        nonpub_goog = set()
        nonpub_nongoog = set()

        public_scan = False
        all_collection = set()
        lending_edition = None
        in_library_edition = None
        lending_ia_identifier = None
        printdisabled = set()
        for e in editions:
            if 'ocaid' not in e:
                continue
            if not lending_edition and 'lendinglibrary' in e.get('ia_collection', []):
                lending_edition = re_edition_key.match(e['key']).group(1)
                lending_ia_identifier = e['ocaid']
            if not in_library_edition and 'inlibrary' in e.get('ia_collection', []):
                in_library_edition = re_edition_key.match(e['key']).group(1)
                lending_ia_identifier = e['ocaid']
            if 'printdisabled' in e.get('ia_collection', []):
                printdisabled.add(re_edition_key.match(e['key']).group(1))
            all_collection.update(e.get('ia_collection', []))
            assert isinstance(e['ocaid'], six.string_types)
            i = e['ocaid'].strip()
            if e.get('public_scan'):
                public_scan = True
                if i.endswith('goog'):
                    pub_goog.add(i)
                else:
                    pub_nongoog.add(i)
            else:
                if i.endswith('goog'):
                    nonpub_goog.add(i)
                else:
                    nonpub_nongoog.add(i)
        ia_list = list(pub_nongoog) + list(pub_goog) + list(nonpub_nongoog) + list(nonpub_goog)
        add("ebook_count_i", len(ia_list))

        has_fulltext = any(e.get('ocaid', None) for e in editions)

        add_list('ia', ia_list)
        if has_fulltext:
            add('public_scan_b', public_scan)
        if all_collection:
            add('ia_collection_s', ';'.join(all_collection))
        if lending_edition:
            add('lending_edition_s', lending_edition)
            add('lending_identifier_s', lending_ia_identifier)
        elif in_library_edition:
            add('lending_edition_s', in_library_edition)
            add('lending_identifier_s', lending_ia_identifier)
        if printdisabled:
            add('printdisabled_s', ';'.join(list(printdisabled)))

def dict2element(d):
    """
    Convert the dict to insert into Solr into Solr XML <doc>.

    :param dict d:
    :rtype: lxml.etree.ElementBase
    """
    doc = Element("doc")
    for k, v in d.items():
        if isinstance(v, (list, set)):
            add_field_list(doc, k, v)
        else:
            add_field(doc, k, v)
    return doc

def build_data(w):
    """
    Construct the Solr document to insert into Solr for the given work

    :param dict w: Work to insert/update
    :rtype: dict
    """
    # Anand - Oct 2013
    # For /works/ia:xxx, editions are already supplied. Querying will empty response.
    if "editions" in w:
        editions = w['editions']
    else:
        editions = data_provider.get_editions_of_work(w)
    authors = SolrProcessor().extract_authors(w)

    iaids = [e["ocaid"] for e in editions if "ocaid" in e]
    ia = dict((iaid, get_ia_collection_and_box_id(iaid)) for iaid in iaids)
    duplicates = {}
    return build_data2(w, editions, authors, ia, duplicates)

def build_data2(w, editions, authors, ia, duplicates):
    """
    Construct the Solr document to insert into Solr for the given work

    :param dict w: Work to get data for
    :param list[dict] editions: Editions of work
    :param list[dict] authors: Authors of work
    :param dict[str, dict[str, set[str]]] ia: boxid/collection of each associated IA id
        (ex: `{foobar: {boxid: {"foo"}, collection: {"lendinglibrary"}}}`)
    :param duplicates: FIXME unused
    :rtype: dict
    """
    resolve_redirects = False

    assert w['type']['key'] == '/type/work'
    # Some works are missing a title, but have titles on their editions
    w['title'] = next(itertools.chain(
        (book['title'] for book in itertools.chain([w], editions) if book.get('title')),
        ['__None__']
    ))
    if w['title'] == '__None__':
        logger.warning('Work missing title %s' % w['key'])

    p = SolrProcessor(resolve_redirects)

    identifiers = defaultdict(list)
    editions = p.process_editions(w, editions, ia, identifiers)

    has_fulltext = any(e.get('ocaid', None) for e in editions)

    subjects = p.get_subject_counts(w, editions, has_fulltext)

    def add_field(doc, name, value):
        doc[name] = value

    def add_field_list(doc, name, field_list):
        doc[name] = list(field_list)

    doc = p.build_data(w, editions, subjects, has_fulltext)

    work_cover_id = next(itertools.chain(
        (cover_id for cover_id in w.get('covers', []) if cover_id != -1),
        [None]
    ))

    cover_edition = pick_cover_edition(editions, work_cover_id)
    if cover_edition:
        cover_edition_key = re_edition_key.match(cover_edition['key']).group(1)
        add_field(doc, 'cover_edition_key', cover_edition_key)

    main_cover_id = work_cover_id or (
        next(cover_id for cover_id in cover_edition['covers'] if cover_id != -1)
        if cover_edition else None)
    if main_cover_id:
        assert isinstance(main_cover_id, int)
        add_field(doc, 'cover_i', main_cover_id)

    k = 'first_sentence'
    fs = set( e[k]['value'] if isinstance(e[k], dict) else e[k] for e in editions if e.get(k, None))
    add_field_list(doc, k, fs)

    publishers = set()
    for e in editions:
        publishers.update('Sine nomine' if is_sine_nomine(i) else i for i in e.get('publishers', []))
    add_field_list(doc, 'publisher', publishers)
#    add_field_list(doc, 'publisher_facet', publishers)

    lang = set()
    ia_loaded_id = set()
    ia_box_id = set()

    for e in editions:
        for l in e.get('languages', []):
            m = re_lang_key.match(l['key'] if isinstance(l, dict) else l)
            lang.add(m.group(1))
        if e.get('ia_loaded_id'):
            if isinstance(e['ia_loaded_id'], six.string_types):
                ia_loaded_id.add(e['ia_loaded_id'])
            else:
                try:
                    assert isinstance(e['ia_loaded_id'], list) and isinstance(e['ia_loaded_id'][0], six.string_types)
                except AssertionError:
                    logger.error("AssertionError: ia=%s, ia_loaded_id=%s", e.get("ia"), e['ia_loaded_id'])
                    raise
                ia_loaded_id.update(e['ia_loaded_id'])
        if e.get('ia_box_id'):
            if isinstance(e['ia_box_id'], six.string_types):
                ia_box_id.add(e['ia_box_id'])
            else:
                try:
                    assert isinstance(e['ia_box_id'], list) and isinstance(e['ia_box_id'][0], six.string_types)
                except AssertionError:
                    logger.error("AssertionError: %s", e['key'])
                    raise
                ia_box_id.update(e['ia_box_id'])
    if lang:
        add_field_list(doc, 'language', lang)

    #if lending_edition or in_library_edition:
    #    add_field(doc, "borrowed_b", is_borrowed(lending_edition or in_library_edition))

    author_keys = [re_author_key.match(a['key']).group(1) for a in authors]
    author_names = [a.get('name', '') for a in authors]
    add_field_list(doc, 'author_key', author_keys)
    add_field_list(doc, 'author_name', author_names)

    alt_names = set()
    for a in authors:
        if 'alternate_names' in a:
            alt_names.update(a['alternate_names'])

    add_field_list(doc, 'author_alternative_name', alt_names)
    add_field_list(doc, 'author_facet', (' '.join(v) for v in zip(author_keys, author_names)))
    #if subjects:
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

    return doc


async def solr_insert_documents(
        documents: List[dict],
        commit_within=60_000,
        solr_base_url: str = None,
        skip_id_check=False,
):
    """
    Note: This has only been tested with Solr 8, but might work with Solr 3 as well.
    """
    solr_base_url = solr_base_url or get_solr_base_url()
    params = {}
    if commit_within is not None:
        params['commitWithin'] = commit_within
    if skip_id_check:
        params['overwrite'] = 'false'
    logger.debug(f"POSTing update to {solr_base_url}/update {params}")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f'{solr_base_url}/update',
            timeout=30,  # seconds; the default timeout is silly short
            params=params,
            headers={'Content-Type': 'application/json'},
            content=json.dumps(documents)
        )
    resp.raise_for_status()


def solr_update(requests, debug=False, commitWithin=60000, solr_base_url: str = None):
    """POSTs a collection of update requests to Solr.
    TODO: Deprecate and remove string requests. Is anything else still generating them?
    :param list[string or UpdateRequest or DeleteRequest] requests: Requests to send to Solr
    :param bool debug:
    :param int commitWithin: Solr commitWithin, in ms
    """
    solr_base_url = solr_base_url or get_solr_base_url()
    url = f'{solr_base_url}/update'
    parsed_url = urlparse(url)
    assert parsed_url.hostname

    if parsed_url.port:
        h1 = HTTPConnection(parsed_url.hostname, parsed_url.port)
    else:
        h1 = HTTPConnection(parsed_url.hostname)
    logger.debug("POSTing update to %s", url)
    # FIXME; commit strategy / timing should be managed in config, not code
    url = url + "?commitWithin=%d" % commitWithin

    h1.connect()
    for r in requests:
        if not isinstance(r, six.string_types):
            # Assuming it is either UpdateRequest or DeleteRequest
            r = r.toxml()
        if not r:
            continue

        if debug:
            logger.info('request: %r', r[:65] + '...' if len(r) > 65 else r)
        assert isinstance(r, six.string_types)
        h1.request('POST', url, r.encode('utf8'), { 'Content-type': 'text/xml;charset=utf-8'})
        response = h1.getresponse()
        response_body = response.read()
        if response.reason != 'OK':
            logger.error(response.reason)
            logger.error(response_body)
        if debug:
            logger.info(response.reason)
    h1.close()

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
            for s in self.get_subject_seeds(work):
                yield s

            if authors is None:
                authors = [a['author'] for a in work.get("authors", [])
                           if 'author' in a and 'key' in a['author']]

        if authors:
            for a in authors:
                yield a['key']

    def get_subject_seeds(self, work):
        """Yields all subject seeds from the work.
        """
        return (
            self._prepare_subject_keys("/subjects/", work.get("subjects")) +
            self._prepare_subject_keys("/subjects/person:", work.get("subject_people")) +
            self._prepare_subject_keys("/subjects/place:", work.get("subject_places")) +
            self._prepare_subject_keys("/subjects/time:", work.get("subject_times")))

    def _prepare_subject_keys(self, prefix, subject_names):
        subject_names = subject_names or []
        return [self.get_subject_key(prefix, s) for s in subject_names]

    def get_subject_key(self, prefix, subject):
        if isinstance(subject, six.string_types):
            key = prefix + self.re_subject.sub("_", subject.lower()).strip("_")
            return key

class EditionBuilder(BaseDocBuilder):
    """Helper to edition solr data.
    """
    def __init__(self, edition, work, authors):
        self.edition = edition
        self.work = work
        self.authors = authors

    def build(self):
        return dict(self._build())

    def _build(self):
        yield 'key', self.edition['key']
        yield 'type', 'edition'
        yield 'title', self.edition.get('title') or ''
        yield 'seed', self.compute_seeds(self.work, [self.edition])

        isbns = self.edition.get("isbn_10", []) + self.edition.get("isbn_13", [])
        isbn_set = set()
        for isbn in isbns:
            isbn_set.add(isbn)
            isbn_set.add(isbn.strip().replace("-", ""))
        yield "isbn", list(isbn_set)

        has_fulltext = bool(self.edition.get("ocaid"))
        yield 'has_fulltext', has_fulltext

        if self.authors:
            author_names = [a.get('name', '') for a in self.authors]
            author_keys = [a['key'].split("/")[-1] for a in self.authors]
            yield 'author_name', author_names
            yield 'author_key', author_keys

        last_modified = datetimestr_to_int(self.edition.get('last_modified'))
        yield 'last_modified_i', last_modified

class SolrRequestSet:
    def __init__(self):
        self.deletes = []
        self.docs = []

    def delete(self, key):
        self.deletes.append(key)

    def add(self, doc):
        self.docs.append(doc)

    def get_requests(self):
        return list(self._get_requests())

    def _get_requests(self):
        requests = []
        requests += [make_delete_query(self.deletes)]
        requests += [self._add_request(doc) for doc in self.docs]
        return requests

    def _add_request(self, doc):
        """Constructs add request using doc dict.
        """
        pass

class UpdateRequest:
    """A Solr <add> request."""

    def __init__(self, doc):
        """
        :param dict doc: Document to be inserted into Solr.
        """
        self.doc = doc

    def toxml(self):
        """
        Create the XML <add> element of this request to send to Solr.

        :rtype: str
        """
        node = dict2element(self.doc)
        root = Element("add")
        root.append(node)
        return tostring(root, encoding="unicode")

    def tojson(self):
        """
        Get a JSON string for the document to insert into Solr.

        :rtype: str
        """
        return json.dumps(self.doc)

class DeleteRequest:
    """A Solr <delete> request."""

    def __init__(self, keys):
        """
        :param list[str] keys: Keys to mark for deletion (ex: ["/books/OL1M"]).
        """
        self.keys = keys

    def toxml(self):
        """
        Create the XML <delete> element of this request to send to Solr.

        :rtype: str or None
        """
        if self.keys:
            return make_delete_query(self.keys)


def solr8_update(
        reqs: List[Union[str, UpdateRequest, DeleteRequest]],
        commit_within=60_000,
        skip_id_check=False,
        solr_base_url: str = None,
) -> None:
    """
    This will replace solr_update once we're fully on Solr 8.7+

    :param commit_within: milliseconds
    """
    req_strs = (r if type(r) == str else r.toxml() for r in reqs if r)  # type: ignore
    # .toxml() can return None :/
    content = f"<update>{''.join(s for s in req_strs if s)}</update>"  # type: ignore

    solr_base_url = solr_base_url or get_solr_base_url()
    params = {}
    if commit_within is not None:
        params['commitWithin'] = commit_within
    if skip_id_check:
        params['overwrite'] = 'false'
    logger.debug(f"POSTing update to {solr_base_url}/update {params}")
    try:
        resp = httpx.post(
            f'{solr_base_url}/update',
            timeout=30,  # The default timeout is silly short
            params=params,
            headers={'Content-Type': 'application/xml'},
            content=content)
        resp.raise_for_status()
    except HTTPError:
        logger.error('Error with solr8 POST update')


def process_edition_data(edition_data):
    """Returns a solr document corresponding to an edition using given edition data.
    """
    builder = EditionBuilder(edition_data['edition'], edition_data['work'], edition_data['authors'])
    return builder.build()

def process_work_data(work_data):
    """Returns a solr document corresponding to a work using the given work_data.
    """
    return build_data2(
        work_data['work'],
        work_data['editions'],
        work_data['authors'],
        work_data['ia'],
        work_data['duplicates'])

def update_edition(e):
    """
    Get the Solr requests necessary to insert/update this edition into Solr.
    Currently editions are not indexed by Solr
    (unless they are orphaned editions passed into update_work() as fake works.
    This always returns an empty list.
    :param dict e: Edition to update
    :rtype: list
    """
    return []

    ekey = e['key']
    logger.debug("updating edition %s", ekey)

    wkey = e.get('works') and e['works'][0]['key']
    w = wkey and data_provider.get_document(wkey)
    authors = []

    if w:
        authors = [data_provider.get_document(a['author']['key']) for a in w.get("authors", []) if 'author' in a]

    request_set = SolrRequestSet()
    request_set.delete(ekey)

    redirect_keys = data_provider.find_redirects(ekey)
    for k in redirect_keys:
        request_set.delete(k)

    doc = EditionBuilder(e, w, authors).build()
    request_set.add(doc)
    return request_set.get_requests()

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
    key = "/subjects/%s:%s" % (subject_type, subject_key)

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
        }).json()

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

def update_subject(key):
    subject = get_subject(key)
    request_set = SolrRequestSet()
    request_set.delete(subject['key'])

    if subject['work_count'] > 0:
        request_set.add(subject)
    return request_set.get_requests()


def subject_name_to_key(
        subject_type: Literal['subject', 'person', 'place', 'time'],
        subject_name: str
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


def update_work(work):
    """
    Get the Solr requests necessary to insert/update this work into Solr.

    :param dict work: Work to insert/update
    :rtype: list[UpdateRequest or DeleteRequest]
    """
    wkey = work['key']
    requests = []

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
            'authors': [{'type': '/type/author_role', 'author': {'key': a['key']}} for a in work.get('authors', [])]
        }
        # Hack to add subjects when indexing /books/ia:xxx
        if work.get("subjects"):
            fake_work['subjects'] = work['subjects']
        return update_work(fake_work)
    elif work['type']['key'] == '/type/work':
        try:
            solr_doc = build_data(work)
            dict2element(solr_doc)
        except:
            logger.error("failed to update work %s", work['key'], exc_info=True)
        else:
            if solr_doc is not None:
                # Delete all ia:foobar keys
                if solr_doc.get('ia'):
                    requests.append(DeleteRequest(["/works/ia:" + iaid for iaid in solr_doc['ia']]))
                requests.append(UpdateRequest(solr_doc))
    elif work['type']['key'] in ['/type/delete', '/type/redirect']:
        requests.append(DeleteRequest([wkey]))
    else:
        logger.error("unrecognized type while updating work %s", wkey)

    return requests


def make_delete_query(keys):
    """
    Create a solr <delete> tag with subelements for each key.

    Example:

    >>> make_delete_query(["/books/OL1M"])
    '<delete><id>/books/OL1M</id></delete>'

    :param list[str] keys: Keys to create delete tags for. (ex: ["/books/OL1M"])
    :return: <delete> XML element as a string
    :rtype: str
    """
    # Escape ":" in keys like "ia:foo00bar"
    keys = [solr_escape(key) for key in keys]
    delete_query = Element('delete')
    for key in keys:
        query = SubElement(delete_query, 'id')
        query.text = key
    return tostring(delete_query, encoding="unicode")

def update_author(akey, a=None, handle_redirects=True):
    """
    Get the Solr requests necessary to insert/update/delete an Author in Solr.
    :param string akey: The author key, e.g. /authors/OL23A
    :param dict a: Optional Author
    :param bool handle_redirects: If true, remove from Solr all authors that redirect to this one
    :rtype: list[UpdateRequest or DeleteRequest]
    """
    if akey == '/authors/':
        return
    m = re_author_key.match(akey)
    if not m:
        logger.error('bad key: %s', akey)
    assert m
    author_id = m.group(1)
    if not a:
        a = data_provider.get_document(akey)
    if a['type']['key'] in ('/type/redirect', '/type/delete') or not a.get('name', None):
        return [DeleteRequest([akey])]
    try:
        assert a['type']['key'] == '/type/author'
    except AssertionError:
        logger.error("AssertionError: %s", a['type']['key'])
        raise

    facet_fields = ['subject', 'time', 'person', 'place']
    base_url = get_solr_base_url() + '/select'

    reply = requests.get(base_url, params=[
        ('wt', 'json'),
        ('json.nl', 'arrarr'),
        ('q', 'author_key:%s' % author_id),
        ('sort', 'edition_count desc'),
        ('row', 1),
        ('fl', 'title,subtitle'),
        ('facet', 'true'),
        ('facet.mincount', 1),
    ] + [
        ('facet.field', '%s_facet' % field) for field in facet_fields
    ]).json()
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
    d = dict(
        key="/authors/" + author_id,
        type='author'
    )

    if a.get('name', None):
        d['name'] = a['name']

    alternate_names = a.get('alternate_names', [])
    if alternate_names:
        d['alternate_names'] = alternate_names

    for f in 'birth_date', 'death_date', 'date':
        if a.get(f, None):
            d[f] = a[f]
    if top_work:
        d['top_work'] = top_work
    d['work_count'] = work_count
    d['top_subjects'] = top_subjects

    solr_requests = []
    if handle_redirects:
        redirect_keys = data_provider.find_redirects(akey)
        #redirects = ''.join('<id>{}</id>'.format(k) for k in redirect_keys)
        # q = {'type': '/type/redirect', 'location': akey}
        # try:
        #     redirects = ''.join('<id>%s</id>' % re_author_key.match(r['key']).group(1) for r in query_iter(q))
        # except AttributeError:
        #     logger.error('AssertionError: redirects: %r', [r['key'] for r in query_iter(q)])
        #     raise
        #if redirects:
        #    solr_requests.append('<delete>' + redirects + '</delete>')
        if redirect_keys:
            solr_requests.append(DeleteRequest(redirect_keys))
    solr_requests.append(UpdateRequest(d))
    return solr_requests


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
        }).json()
    docs = reply['response'].get('docs', [])
    if docs:
        return docs[0]['key'] # /works/ prefix is in solr


def update_keys(keys,
                commit=True,
                output_file=None,
                commit_way_later=False,
                solr8=False,
                skip_id_check=False,
                update: Literal['update', 'print', 'pprint', 'quiet'] = 'update'):
    """
    Insert/update the documents with the provided keys in Solr.

    :param list[str] keys: Keys to update (ex: ["/books/OL1M"]).
    :param bool commit: Create <commit> tags to make Solr persist the changes (and make the public/searchable).
    :param str output_file: If specified, will save all update actions to output_file **instead** of sending to Solr.
        Each line will be JSON object.
        FIXME Updates to editions/subjects ignore output_file and will be sent (only) to Solr regardless.
    :param bool commit_way_later: set to true if you want to add things quickly and add
        them much later
    """
    logger.debug("BEGIN update_keys")
    commit_way_later_dur = 1000 * 60 * 60 * 24 * 5  # 5 days?

    def _solr_update(requests, debug=False, commitWithin=60000):
        if update == 'update':
            commitWithin = commit_way_later_dur if commit_way_later else commitWithin

            if solr8:
                return solr8_update(requests, commitWithin, skip_id_check)
            else:
                return solr_update(requests, debug, commitWithin)
        elif update in ('print', 'pprint'):
            for req in requests:
                import xml.etree.ElementTree as ET
                xml_str = (
                    req.toxml()
                    if isinstance(req, UpdateRequest) or isinstance(req, DeleteRequest)
                    else req)
                if xml_str and update == 'pprint':
                    root = ET.XML(xml_str)
                    ET.indent(root)
                    print(ET.tostring(root, encoding='unicode'))
                else:
                    print(str(xml_str)[:100])
        elif update == 'quiet':
            pass

    global data_provider
    global _ia_db
    if data_provider is None:
        data_provider = get_data_provider('default', _ia_db)

    wkeys = set()

    # To delete the requested keys before updating
    # This is required because when a redirect is found, the original
    # key specified is never otherwise deleted from solr.
    deletes = []

    # Get works for all the editions
    ekeys = set(k for k in keys if k.startswith("/books/"))

    data_provider.preload_documents(ekeys)
    for k in ekeys:
        logger.debug("processing edition %s", k)
        edition = data_provider.get_document(k)

        if edition and edition['type']['key'] == '/type/redirect':
            logger.warn("Found redirect to %s", edition['location'])
            edition = data_provider.get_document(edition['location'])

        # When the given key is not found or redirects to another edition/work,
        # explicitly delete the key. It won't get deleted otherwise.
        if not edition or edition['key'] != k:
            deletes.append(k)

        if not edition:
            logger.warn("No edition found for key %r. Ignoring...", k)
            continue
        elif edition['type']['key'] != '/type/edition':
            logger.info("%r is a document of type %r. Checking if any work has it as edition in solr...", k, edition['type']['key'])
            wkey = solr_select_work(k)
            if wkey:
                logger.info("found %r, updating it...", wkey)
                wkeys.add(wkey)

            if edition['type']['key'] == '/type/delete':
                logger.info("Found a document of type %r. queuing for deleting it solr..", edition['type']['key'])
                # Also remove if there is any work with that key in solr.
                wkeys.add(k)
            else:
                logger.warn("Found a document of type %r. Ignoring...", edition['type']['key'])
        else:
            if edition.get("works"):
                wkeys.add(edition["works"][0]['key'])
                # Make sure we remove any fake works created from orphaned editons
                deletes.append(k.replace('/books/', '/works/'))
            else:
                # index the edition as it does not belong to any work
                wkeys.add(k)

    # Add work keys
    wkeys.update(k for k in keys if k.startswith("/works/"))

    data_provider.preload_documents(wkeys)
    data_provider.preload_editions_of_works(wkeys)

    # update works
    requests = []  # type: list[Union[UpdateRequest, DeleteRequest, str]]
    requests += [DeleteRequest(deletes)]
    for k in wkeys:
        logger.debug("updating work %s", k)
        try:
            w = data_provider.get_document(k)
            requests += update_work(w)
        except:
            logger.error("Failed to update work %s", k, exc_info=True)

    if requests:
        if commit:
            requests += ['<commit />']

        if output_file:
            with open(output_file, "w") as f:
                for r in requests:
                    if isinstance(r, UpdateRequest):
                        f.write(r.tojson())
                        f.write("\n")
        else:
            _solr_update(requests, debug=True)

    # update editions
    requests = []
    for k in ekeys:
        try:
            e = data_provider.get_document(k)
            requests += update_edition(e)
        except:
            logger.error("Failed to update edition %s", k, exc_info=True)
    if requests:
        if commit:
            requests += ['<commit/>']
        _solr_update(requests, debug=True)

    # update authors
    requests = []
    akeys = set(k for k in keys if k.startswith("/authors/"))

    data_provider.preload_documents(akeys)
    for k in akeys:
        logger.debug("updating author %s", k)
        try:
            requests += update_author(k)
        except:
            logger.error("Failed to update author %s", k, exc_info=True)

    if requests:
        if output_file:
            with open(output_file, "w") as f:
                for r in requests:
                    if isinstance(r, UpdateRequest):
                        f.write(r.tojson())
                        f.write("\n")
        else:
            #solr_update(requests, debug=True)
            if commit:
                requests += ['<commit />']
            _solr_update(requests, debug=True, commitWithin=1000)

    # update subjects
    skeys = set(k for k in keys if k.startswith("/subjects/"))
    requests = []
    for k in skeys:
        logger.debug("updating subject %s", k)
        try:
            requests += update_subject(k)
        except:
            logger.error("Failed to update subject %s", k, exc_info=True)
    if requests:
        if commit:
            requests += ['<commit />']
        _solr_update(requests, debug=True)

    logger.debug("END update_keys")


def solr_escape(query):
    """
    Escape special characters in Solr query.

    :param str query:
    :rtype: str
    """
    return re.sub(r'([\s\-+!()|&{}\[\]^"~*?:\\])', r'\\\1', query)

def do_updates(keys):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    update_keys(keys, commit=False)

def load_config(c_config='conf/openlibrary.yml'):
    if not config.runtime_config:
        config.load(c_config)
        config.load_config(c_config)

def load_configs(c_host, c_config, c_data_provider='default'):
    host = web.lstrips(c_host, "http://").strip("/")
    set_query_host(host)

    load_config(c_config)

    global _ia_db
    if 'ia_db' in config.runtime_config:
        _ia_db = get_ia_db(config.runtime_config['ia_db'])

    global data_provider
    if data_provider is None:
        if isinstance(c_data_provider, DataProvider):
            data_provider = c_data_provider
        else:
            data_provider = get_data_provider(c_data_provider, _ia_db)
    return data_provider

def get_ia_db(settings):
    host = settings['host']
    db = settings['db']
    user = settings['user']
    pw = os.popen(settings['pw_file']).read().strip()
    ia_db = web.database(dbn="postgres", host=host, db=db, user=user, pw=pw)
    return ia_db


def main(
        keys: List[str],
        ol_url="http://openlibrary.org",
        ol_config="openlibrary.yml",
        output_file: str = None,
        commit=True,
        profile=False,
        data_provider: Literal['default', 'legacy'] = "default",
        solr_base: str = None,
        update: Literal['update', 'print'] = 'update'
):
    """
    Insert the documents with the given keys into Solr.

    :param keys: The keys of the items to update (ex: /books/OL1M)
    :param ol_url: URL of the openlibrary website
    :param ol_config: Open Library config file
    :param output_file: Where to save output
    :param commit: Whether to also trigger a Solr commit
    :param profile: Profile this code to identify the bottlenecks
    :param data_provider: Name of the data provider to use
    :param solr_base: If wanting to override openlibrary.yml
    :param update: Whether/how to do the actual solr update call
    """
    load_configs(ol_url, ol_config, data_provider)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if solr_base:
        set_solr_base_url(solr_base)

    if profile:
        f = web.profile(update_keys)
        _, info = f(keys, commit)
        print(info)
    else:
        update_keys(keys, commit=commit, output_file=output_file, update=update)


if __name__ == '__main__':
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
    FnToCLI(main).run()
