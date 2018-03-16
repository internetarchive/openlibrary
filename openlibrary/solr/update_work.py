import datetime
import httplib
import logging
import os
import re
import sys
import time
import urllib
import urllib2
from collections import defaultdict
from unicodedata import normalize

import simplejson as json
import web
from lxml.etree import tostring, Element, SubElement

from data_provider import get_data_provider
from infogami.infobase.client import ClientException
from openlibrary import config
from openlibrary.catalog.utils.query import set_query_host, base_url as get_ol_base_url
from openlibrary.core import helpers as h
from openlibrary.core import ia
from openlibrary.utils.isbn import opposite_isbn

logger = logging.getLogger("openlibrary.solr")

re_lang_key = re.compile(r'^/(?:l|languages)/([a-z]{3})$')
re_author_key = re.compile(r'^/(?:a|authors)/(OL\d+A)')
re_bad_char = re.compile('[\x01\x0b\x1a-\x1e]')
re_edition_key = re.compile(r"/books/([^/]+)")
re_iso_date = re.compile(r'^(\d{4})-\d\d-\d\d$')
re_solr_field = re.compile('^[-\w]+$', re.U)
re_year = re.compile(r'(\d{4})$')

data_provider = None
_ia_db = None

solr_host = None

def urlopen(url, data=None):
    version = "%s.%s.%s" % sys.version_info[:3]
    user_agent = 'Mozilla/5.0 (openlibrary; %s) Python/%s' % (__file__, version)
    headers = {
        'User-Agent': user_agent
    }
    req = urllib2.Request(url, data, headers)
    return urllib2.urlopen(req)

def get_solr():
    """
    Get Solr host

    :rtype: str
    """
    global solr_host

    load_config()

    if not solr_host:
        solr_host = config.runtime_config['plugin_worksearch']['solr']

    return solr_host

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
    if not isinstance(s, basestring):
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
        field.text = normalize('NFC', unicode(strip_bad_char(value)))
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

def pick_cover(w, editions):
    """
    Get edition that's used as the cover of the work. Otherwise get the first English edition, or otherwise any edition.

    :param dict w:
    :param list[dict] editions:
    :return: Edition key (ex: "/books/OL1M")
    :rtype: str or None
    """
    w_cover = w['covers'][0] if w.get('covers', []) else None
    first_with_cover = None
    for e in editions:
        if 'covers' not in e:
            continue
        if w_cover and e['covers'][0] == w_cover:
            return e['key']
        if not first_with_cover:
            first_with_cover = e['key']
        for l in e.get('languages', []):
            if 'eng' in l:
                return e['key']
    return first_with_cover

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

    for db_field, solr_field in field_map.iteritems():
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
    for j in (j for j in i.keys() if j not in want):
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
                ia = loaded if isinstance(loaded, basestring) else loaded[0]

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
                if 'ia_box_id' in e and isinstance(e['ia_box_id'], basestring):
                    e['ia_box_id'] = [e['ia_box_id']]
                if ia_meta_fields.get('boxid'):
                    box_id = list(ia_meta_fields['boxid'])[0]
                    e.setdefault('ia_box_id', [])
                    if box_id.lower() not in [x.lower() for x in e['ia_box_id']]:
                        e['ia_box_id'].append(box_id)
                e['ia_collection'] = collection
                e['public_scan'] = ('lendinglibrary' not in collection) and ('printdisabled' not in collection)

            if 'identifiers' in e:
                for k, id_list in e['identifiers'].iteritems():
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
        return sorted(editions, key=lambda e: e.get('pub_year', None))

    def get_author(self, a):
        """
        Get author dict from author entry in the work.

        get_author({"author": {"key": "/authors/OL1A"}})

        :param dict a: An element of work['authors']
        :return: Full author document
        :rtype: dict or None
        """
        # TODO is this still an active problem?
        if 'author' not in a: # OL Web UI bug
            return # http://openlibrary.org/works/OL15365167W.yml?m=edit&v=1

        author = a['author']

        if 'type' in author:
            # means it is already the whole object.
            # It'll be like this when doing re-indexing of solr.
            return author

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
        authors = [self.get_author(a) for a in w.get("authors", [])]

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

        for db_field, solr_field in field_map.iteritems():
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
            assert isinstance(e['ocaid'], basestring)
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
    title = w.get('title', None)
    if not title:
        return

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

    cover_edition = pick_cover(w, editions)
    if cover_edition:
        add_field(doc, 'cover_edition_key', re_edition_key.match(cover_edition).group(1))
    if w.get('covers'):
        cover = w['covers'][0]
        assert isinstance(cover, int)
        add_field(doc, 'cover_i', cover)

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
            if isinstance(e['ia_loaded_id'], basestring):
                ia_loaded_id.add(e['ia_loaded_id'])
            else:
                try:
                    assert isinstance(e['ia_loaded_id'], list) and isinstance(e['ia_loaded_id'][0], basestring)
                except AssertionError:
                    logger.error("AssertionError: ia=%s, ia_loaded_id=%s", e.get("ia"), e['ia_loaded_id'])
                    raise
                ia_loaded_id.update(e['ia_loaded_id'])
        if e.get('ia_box_id'):
            if isinstance(e['ia_box_id'], basestring):
                ia_box_id.add(e['ia_box_id'])
            else:
                try:
                    assert isinstance(e['ia_box_id'], list) and isinstance(e['ia_box_id'][0], basestring)
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
        add_field_list(doc, k, subjects[k].keys())
        add_field_list(doc, k + '_facet', subjects[k].keys())
        subject_keys = [str_to_key(s) for s in subjects[k].keys()]
        add_field_list(doc, k + '_key', subject_keys)

    for k in sorted(identifiers.keys()):
        add_field_list(doc, 'id_' + k, identifiers[k])

    if ia_loaded_id:
        add_field_list(doc, 'ia_loaded_id', ia_loaded_id)

    if ia_box_id:
        add_field_list(doc, 'ia_box_id', ia_box_id)

    return doc

def solr_update(requests, debug=False, commitWithin=60000):
    """POSTs a collection of update requests to Solr.
    TODO: Deprecate and remove string requests. Is anything else still generating them?
    :param list[string or UpdateRequest or DeleteRequest] requests: Requests to send to Solr
    :param bool debug:
    :param int commitWithin: Solr commitWithin, in ms
    """
    h1 = httplib.HTTPConnection(get_solr())
    url = 'http://%s/solr/update' % get_solr()

    logger.info("POSTing update to %s", url)
    url = url + "?commitWithin=%d" % commitWithin

    h1.connect()
    for r in requests:
        if not isinstance(r, basestring):
            # Assuming it is either UpdateRequest or DeleteRequest
            r = r.toxml()
        if not r:
            continue

        if debug:
            logger.info('request: %r', r[:65] + '...' if len(r) > 65 else r)
        assert isinstance(r, basestring)
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
        if isinstance(subject, basestring):
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
        return tostring(root).encode('utf-8')

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
    logger.info("updating edition %s", ekey)

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

    params = {
        'wt': 'json',
        'json.nl': 'arrarr',
        'q': '%s:%s' % (search_field, subject_key),
        'rows': '0',
        'facet': 'true',
        'facet.field': facet_field,
        'facet.mincount': 1,
        'facet.limit': 100
    }
    base_url = 'http://' + get_solr() + '/solr/select'
    url = base_url + '?' + urllib.urlencode(params)
    result = json.load(urlopen(url))

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

def update_work(w, debug=False):
    """
    Get the Solr requests necessary to insert/update this work into Solr.

    :param dict w: Work to insert/update
    :param bool debug: FIXME unused
    :rtype: list[UpdateRequest or DeleteRequest]
    """
    wkey = w['key']
    deletes = []
    requests = []

    # q = {'type': '/type/redirect', 'location': wkey}
    # redirect_keys = [r['key'][7:] for r in query_iter(q)]
    # redirect_keys = [k[7:] for k in data_provider.find_redirects(wkey)]

    # deletes += redirect_keys
    # deletes += [wkey[7:]] # strip /works/ from /works/OL1234W

    # Handle edition records as well
    # When an edition does not contain a works list, create a fake work and index it.
    if w['type']['key'] == '/type/edition' and w.get('title'):
        edition = w
        w = {
            # Use key as /works/OL1M.
            # In solr we are using full path as key. So it is required to be
            # unique across all types of documents. The website takes care of
            # redirecting /works/OL1M to /books/OL1M.
            'key': edition['key'].replace("/books/", "/works/"),
            'type': {'key': '/type/work'},
            'title': edition['title'],
            'editions': [edition],
            'authors': [{'type': '/type/author_role', 'author': {'key': a['key']}} for a in edition.get('authors', [])]
        }
        # Hack to add subjects when indexing /books/ia:xxx
        if edition.get("subjects"):
            w['subjects'] = edition['subjects']

    if w['type']['key'] == '/type/work' and w.get('title'):
        try:
            d = build_data(w)
            dict2element(d)
        except:
            logger.error("failed to update work %s", w['key'], exc_info=True)
        else:
            if d is not None:
                # Delete all ia:foobar keys
                if d.get('ia'):
                    deletes += ["ia:" + iaid for iaid in d['ia']]

                # In solr, we use full path as key, not just the last part
                deletes = ["/works/" + k for k in deletes]

                requests.append(DeleteRequest(deletes))
                requests.append(UpdateRequest(d))
    elif w['type']['key'] == '/type/delete':
        # Delete the record from solr if the work has been deleted in OL.
        deletes += [wkey[7:]] # strip /works/ from /works/OL1234W

        # In solr, we use full path as key, not just the last part
        deletes = ["/works/" + k for k in deletes]
        requests.append(DeleteRequest(deletes))

    return requests

def make_delete_query(keys):
    """
    Create a solr <delete> tag with subelements for each key.

    Example:

    >>> make_delete_query(["/books/OL1M"])
    "<delete><query>key:/books/OL1M</query></delete>"

    :param list[str] keys: Keys to create delete tags for. (ex: ["/books/OL1M"])
    :return: <delete> XML element as a string
    :rtype: str
    """
    # Escape ":" in keys like "ia:foo00bar"
    keys = [solr_escape(key) for key in keys]
    delete_query = Element('delete')
    for key in keys:
        query = SubElement(delete_query,'query')
        query.text = 'key:%s' % key
    return tostring(delete_query)

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
    base_url = 'http://' + get_solr() + '/solr/select'

    url = base_url + '?wt=json&json.nl=arrarr&q=author_key:%s&sort=edition_count+desc&rows=1&fl=title,subtitle&facet=true&facet.mincount=1' % author_id
    url += ''.join('&facet.field=%s_facet' % f for f in facet_fields)

    logger.info("urlopen %s", url)

    reply = json.load(urlopen(url))
    work_count = reply['response']['numFound']
    docs = reply['response'].get('docs', [])
    top_work = None
    if docs:
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

    for f in 'birth_date', 'death_date', 'date':
        if a.get(f, None):
            d[f] = a[f]
    if top_work:
        d['top_work'] = top_work
    d['work_count'] = work_count
    d['top_subjects'] = top_subjects

    requests = []
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
        #    requests.append('<delete>' + redirects + '</delete>')
        if redirect_keys:
            requests.append(DeleteRequest(redirect_keys))
    requests.append(UpdateRequest(d))
    return requests

def get_document(key):
    url = get_ol_base_url() + key + ".json"
    for i in range(10):
        try:
            logger.info("urlopen %s", url)
            contents = urlopen(url).read()
            return json.loads(contents)
        except urllib2.HTTPError, e:
            contents = e.read()
            # genuine 404, not a server error
            if e.getcode() == 404 and '"error": "notfound"' in contents:
                return {"key": key, "type": {"key": "/type/delete"}}

        print >> sys.stderr, "Failed to get document from %s" % url
        print >> sys.stderr, "retry", i

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

    url = 'http://' + get_solr() + '/solr/select?wt=json&q=edition_key:%s&rows=1&fl=key' % edition_key
    reply = json.load(urlopen(url))
    docs = reply['response'].get('docs', [])
    if docs:
        return docs[0]['key'] # /works/ prefix is in solr

def update_keys(keys, commit=True, output_file=None):
    """
    Insert/update the documents with the provided keys in Solr.

    :param list[str] keys: Keys to update (ex: ["/books/OL1M"]).
    :param bool commit: Create <commit> tags to make Solr persist the changes (and make the public/searchable).
    :param str output_file: If specified, will save all update actions to output_file **instead** of sending to Solr.
        Each line will be JSON object.
        FIXME Updates to editions/subjects ignore output_file and will be sent (only) to Solr regardless.
    """
    logger.info("BEGIN update_keys")

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
        logger.info("processing edition %s", k)
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
            else:
                # index the edition as it does not belong to any work
                wkeys.add(k)

    # Add work keys
    wkeys.update(k for k in keys if k.startswith("/works/"))

    data_provider.preload_documents(wkeys)
    data_provider.preload_editions_of_works(wkeys)

    # update works
    requests = []
    requests += [DeleteRequest(deletes)]
    for k in wkeys:
        logger.info("updating %s", k)
        try:
            w = data_provider.get_document(k)
            requests += update_work(w, debug=True)
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
            solr_update(requests, debug=True)

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
        solr_update(requests, debug=True)

    # update authors
    requests = []
    akeys = set(k for k in keys if k.startswith("/authors/"))

    data_provider.preload_documents(akeys)
    for k in akeys:
        logger.info("updating %s", k)
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
            solr_update(requests, debug=True, commitWithin=1000)

    # update subjects
    skeys = set(k for k in keys if k.startswith("/subjects/"))
    requests = []
    for k in skeys:
        logger.info("updating %s", k)
        try:
            requests += update_subject(k)
        except:
            logger.error("Failed to update subject %s", k, exc_info=True)
    if requests:
        if commit:
            requests += ['<commit />']
        solr_update(requests, debug=True)

    logger.info("END update_keys")

def new_query_iter(q, limit=500, offset=0):
    """Alternative implementation of query_iter, that talks to the
    database directly instead of accessing the website API.

    This is set to `query_iter` when this script is called with
    --monkeypatch option.
    """
    q['limit'] = limit
    q['offset'] = offset
    site = web.ctx.site

    while True:
        keys = site.things(q)
        logger.info("query_iter %s", q)
        docs = keys and site.get_many(keys, raw=True)
        for doc in docs:
            yield doc

        # We haven't got as many we have requested. No point making one more request
        if len(keys) < limit:
            break
        q['offset'] += limit


class MonkeyPatch:
    """Utility to monkeypatch many of the functions used here with faster alternatives.
    """
    def __init__(self):
        self.cache = {}
        self.redirect_cache = {}
        self.ia_cache = {}
        self.ia_redirect_cache = {}

        from openlibrary.solr.process_stats import get_ia_db, get_db
        self.db = get_db()
        self.ia_db = get_ia_db()
        self.count_withKey = 0

    def clear_cache(self, max_size=10000):
        """Clears all the caches when size of the largest cache has more than max_size elements.

        Useful to avoid building up memory for long running solr updater.
        """
        caches = [self.cache, self.redirect_cache, self.ia_cache, self.ia_redirect_cache]
        size = max(len(c) for c in caches)
        if size > max_size:
            logger.info("clearing monkey patch cache. size of largest cache is %s (> %s)",
                        size,
                        max_size)
            for c in caches:
                c.clear()
        else:
            logger.info("not clearing monkey patch cache. size of largest cache small enough. %s (< %s)", size, max_size)

    def monkeypatch(self):
        global query_iter, withKey, get_document, get_ia_collection_and_box_id, find_redirects

        query_iter = new_query_iter
        get_document = self.get_document
        withKey = self.withKey
        get_ia_collection_and_box_id = self.get_ia_collection_and_box_id
        ia.get_metadata = self.get_metadata
        find_redirects = self.find_redirects

    def withKey(self, key):
        """Alternative implementation of withKey, that talks to the database
        directly instead of using the website API.

        This is set to `withKey` when this script is called with --monkeypatch
        option.
        """
        logger.info("withKey %s", key)
        if key not in self.cache:
            self.cache[key] = self.withKey0(key)
        return self.cache[key]

    def withKey0(self, key):
        logger.info("withKey0 %s", key)
        if key.startswith("/books/ia:"):
            itemid = key[len("/books/ia:"):]
            self.preload_ia_redirect_cache([itemid])
            redirect = self.ia_redirect_cache[itemid]
            if redirect:
                logger.info("withKey0 found redirect %s -> %s", key, redirect)
                return self.withKey(redirect)

            logger.info("withKey0 no redirect found %s", key)
            metadata = self.get_metadata(itemid)
            return ia.edition_from_item_metadata(itemid, metadata)
        else:
            self.count_withKey += 1
            logger.info("withKey0 infoabse request %s (%s)", key, self.count_withKey)
            return web.ctx.site._request('/get', data={'key': key})

    def get_document(self, key):
        try:
            return self.withKey(key)
        except ClientException, e:
            if e.status.startswith('404'):
                logger.warn("%s is not found, considering it as deleted.", key)
                return {"key": key, "type": {"key": "/type/delete"}}
            else:
                raise

    def preload_keys(self, keys):
        identifiers = [k.replace("/books/ia:", "") for k in keys if k.startswith("/books/ia:")]
        self.preload_ia_items(identifiers)
        re_key = web.re_compile("/(books|works|authors)/OL\d+[MWA]")

        keys2 = set(k for k in keys if re_key.match(k))
        keys2.update(k for k in self.ia_redirect_cache.values() if k is not None)
        self.preload_keys0(keys2)
        self._preload_works()
        self._preload_authors()

        keys3 = [k for k in self.cache if k.startswith("/works/") or k.startswith("/authors/")]
        self.populate_redirect_cache(keys3)

    def preload_keys0(self, keys):
        keys = [k for k in keys if k not in self.cache]
        if not keys:
            return
        for chunk in web.group(keys, 100):
            docs = web.ctx.site.get_many(list(chunk))
            for doc in docs:
                self.cache[doc['key']] = doc.dict()

    def _preload_works(self):
        """Preloads works for all editions in the cache.
        """
        keys = []
        for doc in self.cache.values():
            if doc and doc['type']['key'] == '/type/edition' and doc.get('works'):
                print "success"
                keys.append(doc['works'][0]['key'])
        self.preload_keys0(keys)

    def _preload_authors(self):
        """Preloads authors for all works in the cache.
        """
        keys = []
        for doc in self.cache.values():
            if doc and doc['type']['key'] == '/type/work' and doc.get('authors'):
                keys.extend(a['author']['key'] for a in doc['authors'])
        self.preload_keys0(list(set(keys)))

    def get_metadata(self, itemid):
        """Alternate implementation of ia.get_metadata() that uses IA db directly.
        """
        self.preload_ia_items([itemid])
        if itemid in self.ia_cache:
            d = web.storage(self.ia_cache[itemid])
            d.publisher = d.publisher and d.publisher.split(";")
            d.collection = d.collection and d.collection.split(";")
            d.isbn = d.isbn and d.isbn.split(";")
            d.creator = d.creator and d.creator.split(";")
            return d

    def get_ia_collection_and_box_id(self, itemid):
        """Alternative implementation of get_ia_collection_and_box_id, that talks
        to the archive.org database directly instead of using the metadata API.

        This is set to `get_ia_collection_and_box_id` when this script is called
        with --monkeypatch option.
        """
        metadata = self.get_metadata(itemid)
        if metadata:
            d = {'boxid': set()}
            if metadata.boxid:
                d['boxid'].add(metadata.boxid)
            d['collection'] = set(metadata.collection)
            return d

    def find_redirects(self, key):
        """Returns all the keys that are redirected to this.
        """
        self.populate_redirect_cache([key])
        return self.redirect_cache[key]

    def populate_redirect_cache(self, keys):
        keys = [k for k in keys if k not in self.redirect_cache]
        if not keys:
            return

        for chunk in web.group(keys, 100):
            self.preload_redirect_cache0(list(chunk))

    def preload_redirect_cache0(self, keys):
        query = {
            "type": "/type/redirect",
            "location": keys,
            "a:location": None # asking it to fill location in results
        }
        for k in keys:
            self.redirect_cache.setdefault(k, [])

        matches = web.ctx.site.things(query, details=True)
        for thing in matches:
            # we are trying to find documents that are redirecting to each of the given keys
            self.redirect_cache[thing.location].append(thing.key)

    def preload_ia_redirect_cache(self, identifiers):
        # only consider the ones that are not already in the cache
        identifiers = [id for id in identifiers if id not in self.ia_redirect_cache]
        if not identifiers:
            return
        for chunk in web.group(identifiers, 100):
            self.preload_ia_redirect_cache0(list(chunk))

    def preload_ia_redirect_cache0(self, identifiers):
        # query by ocaid
        query = {
            "type": "/type/edition",
            "ocaid": identifiers,
            "a:ocaid": None # asking it to fill ocaid in results
        }
        matches = web.ctx.site.things(query, details=True)
        for thing in matches:
            #self.cache[thing.key] = thing
            self.ia_redirect_cache[thing.ocaid] = thing.key

        # query by source_records
        query = {
            "type": "/type/edition",
            "source_records": ["ia:" + x for x in identifiers],
            "a:source_records": None # asking it to fill source_records in results
        }
        matches = web.ctx.site.things(query, details=True)
        # print matches
        for thing in matches:
            #self.cache[thing.key] = thing
            for record in thing.source_records:
                if record.startswith("ia:"):
                    itemid = record[len("ia:"):]
                    self.ia_redirect_cache[itemid] = thing.key

        # set None in redirect_cache to indicate that there is no redirect
        for itemid in identifiers:
            self.ia_redirect_cache.setdefault(itemid, None)

    def preload_ia_items(self, identifiers):
        identifiers = [id for id in identifiers if id not in self.ia_cache]
        if not identifiers:
            return

        # print "preload_ia_items", identifiers

        fields = ('identifier, boxid, isbn, ' +
                  'title, description, publisher, creator, ' +
                  'date, collection, ' +
                  'repub_state, mediatype, noindex')

        from openlibrary.solr.process_stats import get_ia_db
        db = get_ia_db()
        rows = db.select('metadata',
            what=fields,
            where='identifier IN $identifiers',
            vars=locals())
        for row in rows:
            self.ia_cache[row.identifier] = row

        self.preload_ia_redirect_cache(identifiers)

_monkeypatch = None

def monkeypatch(config_file):
    """Monkeypatch query functions to avoid hitting openlibrary.org.
    """
    def load_infogami(config_file):
        import infogami
        from infogami import config
        from infogami.utils import delegate

        config.plugin_path += ['openlibrary.plugins']
        config.site = "openlibrary.org"

        infogami.load_config(config_file)
        setup_infobase_config(config_file)

        infogami._setup()
        delegate.fakeload()

    def setup_infobase_config(config_file):
        """Reads the infoabse config file and assign it to config.infobase.
        The config_file is used as base to resolve relative path, if specified in the config.
        """
        from infogami import config
        import os
        import yaml

        if config.get("infobase_config_file"):
            dir = os.path.dirname(config_file)
            path = os.path.join(dir, config.infobase_config_file)
            config.infobase = yaml.safe_load(open(path).read())

    global _monkeypatch
    load_infogami(config_file)

    _monkeypatch = MonkeyPatch()
    _monkeypatch.monkeypatch()

def clear_monkeypatch_cache(max_size=10000):
    if _monkeypatch:
        _monkeypatch.clear_cache(max_size=max_size)

def solr_escape(query):
    """
    Escape special characters in Solr query.

    :param str query:
    :rtype: str
    """
    return re.sub('([\s\-+!()|&{}\[\]^\"~*?:\\\\])', r'\\\1', query)

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
    if 'ia_db' in config.runtime_config.keys():
        _ia_db = get_ia_db(config.runtime_config['ia_db'])

    global data_provider
    if data_provider is None:
        data_provider = get_data_provider(c_data_provider, _ia_db)
    return data_provider

def get_ia_db(settings):
    host = settings['host']
    db = settings['db']
    user = settings['user']
    pw = os.popen(settings['pw_file']).read().strip()
    ia_db = web.database(dbn="postgres", host=host, db=db, user=user, pw=pw)
    return ia_db

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(
        description="Insert the documents with the given keys into Solr",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("keys", nargs="+", help="The keys of the items to update (ex: /books/OL1M")
    parser.add_argument("-s", "--server", default="http://openlibrary.org/", help="URL of the openlibrary website")
    parser.add_argument("-c", "--config", default="openlibrary.yml", help="Open Library config file")
    parser.add_argument("-o", "--output-file", help="Open Library config file")
    parser.add_argument("--nocommit", action="store_true", help="Don't commit to solr")
    parser.add_argument("--monkeypatch", action="store_true", help="Monkeypatch query functions to access DB directly")
    parser.add_argument("--profile", action="store_true", help="Profile this code to identify the bottlenecks")
    parser.add_argument("--data-provider", default='default', help="Name of the data provider to use")

    return parser.parse_args()

def main():
    args = parse_args()
    keys = args.keys

    if args.monkeypatch:
        monkeypatch(args.config)

    load_configs(args.server, args.config, args.data_provider)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.profile:
        f = web.profile(update_keys)
        _, info = f(keys, not args.nocommit)
        print info
    else:
        update_keys(keys, commit=not args.nocommit, output_file=args.output_file)

if __name__ == '__main__':
    main()
