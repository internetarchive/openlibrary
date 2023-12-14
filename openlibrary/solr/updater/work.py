from collections import defaultdict
from collections.abc import Iterable
import datetime
import itertools
import logging
from math import ceil
import re
from statistics import median
import sys
import time
from typing import Any, Optional, cast
from openlibrary.core import helpers as h
import openlibrary.book_providers as bp
from openlibrary.plugins.upstream.utils import safeget
from openlibrary.solr.solr_types import SolrDocument
from openlibrary.solr.update_edition import EditionSolrBuilder, build_edition_data
from openlibrary.solr.updater.abstract import AbstractSolrUpdater
from openlibrary.solr.utils import SolrUpdateRequest, get_solr_next, str_to_key
from openlibrary.utils import uniq
from openlibrary.utils.ddc import choose_sorting_ddc, normalize_ddc
from openlibrary.utils.lcc import choose_sorting_lcc, short_lcc_to_sortable_lcc

logger = logging.getLogger("openlibrary.solr")

re_author_key = re.compile(r'^/(?:a|authors)/(OL\d+A)')
re_edition_key = re.compile(r"/books/([^/]+)")
re_solr_field = re.compile(r'^[-\w]+$', re.U)
re_year = re.compile(r'\b(\d{4})\b')


class WorkSolrUpdater(AbstractSolrUpdater):
    key_prefix = '/works/'
    thing_type = '/type/work'

    async def preload_keys(self, keys: Iterable[str]):
        from openlibrary.solr.update_work import data_provider

        await super().preload_keys(keys)
        data_provider.preload_editions_of_works(keys)

    async def update_key(self, work: dict) -> tuple[SolrUpdateRequest, list[str]]:
        """
        Get the Solr requests necessary to insert/update this work into Solr.

        :param dict work: Work to insert/update
        """
        wkey = work['key']
        update = SolrUpdateRequest()

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

        return update, []


async def build_data(
    w: dict,
    ia_metadata: dict[str, Optional['bp.IALiteMetadata']] | None = None,
) -> SolrDocument:
    """
    Construct the Solr document to insert into Solr for the given work

    :param w: Work to insert/update
    :param ia_metadata: boxid/collection of each associated IA id
        (ex: `{foobar: {boxid: {"foo"}, collection: {"lendinglibrary"}}}`)
    """
    # Anand - Oct 2013
    # For /works/ia:xxx, editions are already supplied. Querying will empty response.
    from openlibrary.solr.update_work import data_provider

    if "editions" in w:
        editions = w['editions']
    else:
        editions = data_provider.get_editions_of_work(w)
    authors = await SolrProcessor().extract_authors(w)

    if ia_metadata is None:
        iaids = [e["ocaid"] for e in editions if "ocaid" in e]
        ia_metadata = {iaid: get_ia_collection_and_box_id(iaid) for iaid in iaids}

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

    p = SolrProcessor()

    identifiers: dict[str, list] = defaultdict(list)
    editions = p.process_editions(w, editions, ia_metadata, identifiers)

    def add_field(doc, name, value):
        doc[name] = value

    def add_field_list(doc, name, field_list):
        doc[name] = list(field_list)

    doc = p.build_data(w, editions, ia_metadata)

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


def get_ia_collection_and_box_id(ia: str) -> Optional['bp.IALiteMetadata']:
    """
    Get the collections and boxids of the provided IA id

    TODO Make the return type of this a namedtuple so that it's easier to reference
    :param str ia: Internet Archive ID
    :return: A dict of the form `{ boxid: set[str], collection: set[str] }`
    :rtype: dict[str, set]
    """
    from openlibrary.solr.update_work import data_provider

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


class SolrProcessor:
    """Processes data to into a form suitable for adding to works solr."""

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
        from openlibrary.solr.update_work import data_provider

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
            author
            for a in SolrProcessor.normalize_authors(w.get("authors", []))
            if (author := await self.get_author(a))
        ]

        if any(a['type']['key'] == '/type/redirect' for a in authors):
            # we don't want to raise an exception but just write a warning on the log
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


def extract_edition_olid(key: str) -> str:
    m = re_edition_key.match(key)
    if not m:
        raise ValueError(f'Invalid key: {key}')
    return m.group(1)


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
