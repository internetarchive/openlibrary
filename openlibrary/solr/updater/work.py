import datetime
import itertools
import logging
import re
import time
from collections import defaultdict
from collections.abc import Iterable
from functools import cached_property
from math import ceil
from statistics import median
from typing import Optional, TypedDict, cast

import openlibrary.book_providers as bp
from openlibrary.core import helpers as h
from openlibrary.core.ratings import WorkRatingsSummary
from openlibrary.plugins.upstream.utils import safeget
from openlibrary.plugins.worksearch.subjects import SubjectPseudoKey
from openlibrary.solr.data_provider import DataProvider, WorkReadingLogSolrSummary
from openlibrary.solr.solr_types import SolrDocument
from openlibrary.solr.updater.abstract import AbstractSolrBuilder, AbstractSolrUpdater
from openlibrary.solr.updater.edition import EditionSolrBuilder
from openlibrary.solr.utils import SolrUpdateRequest, str_to_key
from openlibrary.utils import uniq
from openlibrary.utils.ddc import choose_sorting_ddc, normalize_ddc
from openlibrary.utils.lcc import choose_sorting_lcc, short_lcc_to_sortable_lcc
from openlibrary.utils.open_syllabus_project import get_total_by_olid

logger = logging.getLogger("openlibrary.solr")

re_author_key = re.compile(r'^/(?:a|authors)/(OL\d+A)')
re_edition_key = re.compile(r"/books/([^/]+)")
re_subject = re.compile("[, _]+")


class WorkSolrUpdater(AbstractSolrUpdater):
    key_prefix = '/works/'
    thing_type = '/type/work'

    async def preload_keys(self, keys: Iterable[str]):
        await super().preload_keys(keys)
        self.data_provider.preload_editions_of_works(keys)

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
                # Anand - Oct 2013
                # For /works/ia:xxx, editions are already supplied. Querying will empty response.

                # Fetch editions
                if "editions" in work:
                    editions = work['editions']
                else:
                    editions = self.data_provider.get_editions_of_work(work)

                # Fetch authors
                author_keys = [
                    author['author']['key']
                    for author in normalize_authors(work.get('authors', []))
                ]
                authors = [
                    await self.data_provider.get_document(key) for key in author_keys
                ]
                if any(a['type']['key'] != '/type/author' for a in authors):
                    # we don't want to raise an exception but just write a warning on the log
                    logger.warning('Unexpected author type error: %s', work['key'])
                authors = [a for a in authors if a['type']['key'] == '/type/author']

                # Fetch ia_metadata
                iaids = [e["ocaid"] for e in editions if "ocaid" in e]
                ia_metadata = {
                    iaid: get_ia_collection_and_box_id(iaid, self.data_provider)
                    for iaid in iaids
                }

                solr_doc = WorkSolrBuilder(
                    work, editions, authors, self.data_provider, ia_metadata
                ).build()
            except:  # noqa: E722
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


def get_ia_collection_and_box_id(
    ia: str, data_provider: DataProvider
) -> Optional['bp.IALiteMetadata']:
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


class KeyDict(TypedDict):
    key: str


class NormalizedAuthor(TypedDict):
    type: KeyDict
    author: KeyDict


def normalize_authors(authors: list[dict]) -> list[NormalizedAuthor]:
    """
    Need to normalize to a predictable format because of inconsistencies in data

    >>> normalize_authors([
    ...     {'type': {'key': '/type/author_role'}, 'author': '/authors/OL1A'}
    ... ])
    [{'type': {'key': '/type/author_role'}, 'author': {'key': '/authors/OL1A'}}]
    >>> normalize_authors([{
    ...     "type": {"key": "/type/author_role"},
    ...     "author": {"key": "/authors/OL1A"}
    ... }])
    [{'type': {'key': '/type/author_role'}, 'author': {'key': '/authors/OL1A'}}]
    """
    return [
        cast(
            NormalizedAuthor,
            {
                'type': {'key': safeget(lambda: a['type']['key'], '/type/author_role')},
                'author': (
                    a['author']
                    if isinstance(a['author'], dict)
                    else {'key': a['author']}
                ),
            },
        )
        for a in authors
        # TODO: Remove after
        #  https://github.com/internetarchive/openlibrary-client/issues/126
        if 'author' in a
    ]


def extract_edition_olid(key: str) -> str:
    m = re_edition_key.match(key)
    if not m:
        raise ValueError(f'Invalid key: {key}')
    return m.group(1)


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
            t = datetime.datetime.now()
    else:
        t = datetime.datetime.now()

    return int(time.mktime(t.timetuple()))


def subject_name_to_key(subject_type: str, name: str) -> SubjectPseudoKey:
    prefix = '/subjects/'
    if subject_type != 'subject':
        prefix += f'{subject_type}:'
    return prefix + re_subject.sub("_", name.lower()).strip("_")


class WorkSolrBuilder(AbstractSolrBuilder):
    def __init__(
        self,
        work: dict,
        editions: list[dict],
        authors: list[dict],
        data_provider: DataProvider,
        ia_metadata: dict[str, Optional['bp.IALiteMetadata']],
    ):
        self._work = work
        self._editions = editions
        self._authors = authors
        self._ia_metadata = ia_metadata
        self._data_provider = data_provider
        self._solr_editions = [
            EditionSolrBuilder(
                e, self, self._ia_metadata.get(e.get('ocaid', '').strip())
            )
            for e in self._editions
        ]

    def build(self) -> SolrDocument:
        doc = cast(dict, super().build())
        doc |= self.build_identifiers()
        doc |= self.build_subjects()
        doc |= self.build_legacy_ia_fields()
        doc |= self.build_ratings() or {}
        doc |= self.build_reading_log() or {}

        return cast(SolrDocument, doc)

    @property
    def key(self):
        return self._work['key']

    @property
    def type(self):
        return 'work'

    @property
    def seed(self) -> list[str]:
        w = self._work
        return uniq(
            itertools.chain(
                (e.key for e in self._solr_editions),
                (self.key,),
                (author['key'] for author in self._authors),
                (subject_name_to_key("subject", s) for s in w.get("subjects", [])),
                (subject_name_to_key("person", s) for s in w.get("subject_people", [])),
                (subject_name_to_key("place", s) for s in w.get("subject_places", [])),
                (subject_name_to_key("time", s) for s in w.get("subject_times", [])),
            )
        )

    @property
    def title(self) -> str | None:
        if self._work.get('title'):
            return self._work['title']
        else:
            # Some works are missing a title, but have titles on their editions
            logger.warning('Work missing title %s' % self.key)
            return next(
                (ed.title for ed in self._solr_editions if ed.title), '__None__'
            )

    @property
    def subtitle(self) -> str | None:
        return self._work.get('subtitle')

    @property
    def alternative_title(self) -> set[str]:
        alt_title_set = set()
        for book in (EditionSolrBuilder(self._work), *self._solr_editions):
            alt_title_set.update(book.alternative_title)
            if book.translation_of:
                alt_title_set.add(book.translation_of)
        return alt_title_set

    @property
    def alternative_subtitle(self) -> set[str]:
        """Get subtitles from the editions as alternative titles."""
        return {
            bookish['subtitle'] for bookish in self._editions if bookish.get('subtitle')
        }

    @property
    def edition_count(self) -> int:
        return len(self._editions)

    @property
    def osp_count(self) -> int | None:
        return get_total_by_olid(self.key)

    @property
    def edition_key(self) -> list[str]:
        return [extract_edition_olid(e['key']) for e in self._editions]

    @property
    def by_statement(self) -> set[str]:
        return {e["by_statement"] for e in self._editions if "by_statement" in e}

    @property
    def publish_date(self) -> set[str]:
        return {e.publish_date for e in self._solr_editions if e.publish_date}

    @property
    def publish_year(self) -> set[int]:
        return {
            year for e in self._solr_editions if (year := e.publish_year) is not None
        }

    @property
    def first_publish_year(self) -> int | None:
        if publish_years := self.publish_year:
            return min(publish_years)
        else:
            return None

    @property
    def number_of_pages_median(self) -> int | None:
        number_of_pages = [
            pages
            for e in self._solr_editions
            if (pages := e.number_of_pages) is not None
        ]

        if number_of_pages:
            return ceil(median(number_of_pages))
        else:
            return None

    @property
    def editions(self) -> list[SolrDocument]:
        return [ed.build() for ed in self._solr_editions]

    @property
    def lccn(self) -> set[str]:
        return {lccn for ed in self._solr_editions for lccn in ed.lccn}

    @property
    def publish_place(self) -> set[str]:
        return {v for e in self._editions for v in e.get('publish_places', [])}

    @property
    def oclc(self) -> set[str]:
        return {v for e in self._editions for v in e.get('oclc_numbers', [])}

    @property
    def contributor(self) -> set[str]:
        return {
            v
            for e in self._editions
            for v in (
                e.get('contributions', [])
                # TODO: contributors wasn't included here in the past, but
                # we likely want it to be edition-only if possible?
                # Excluding for now to avoid a possible perf hit in the
                # next full reindex which is already pretty loaded
                # + [c.get('name') for c in e.get('contributors', [])]
            )
            if v
        }

    @property
    def lcc(self) -> set[str]:
        raw_lccs = {
            lcc for ed in self._editions for lcc in ed.get('lc_classifications', [])
        }
        return {lcc for lcc in map(short_lcc_to_sortable_lcc, raw_lccs) if lcc}

    @property
    def lcc_sort(self) -> str | None:
        if lccs := self.lcc:
            return choose_sorting_lcc(lccs)
        else:
            return None

    @property
    def ddc(self) -> set[str]:
        raw_ddcs = {ddc for ed in self._editions for ddc in get_edition_ddcs(ed)}
        return {ddc for raw_ddc in raw_ddcs for ddc in normalize_ddc(raw_ddc) if ddc}

    @property
    def ddc_sort(self) -> str | None:
        if ddcs := self.ddc:
            return choose_sorting_ddc(ddcs)
        else:
            return None

    @property
    def isbn(self) -> set[str]:
        return {isbn for ed in self._editions for isbn in EditionSolrBuilder(ed).isbn}

    @property
    def last_modified_i(self) -> int:
        return max(
            datetimestr_to_int(doc.get('last_modified'))
            for doc in (self._work, *self._editions)
        )

    @property
    def ebook_count_i(self) -> int:
        return sum(
            1 for e in self._solr_editions if e.ebook_access > bp.EbookAccess.NO_EBOOK
        )

    @cached_property
    def ebook_access(self) -> bp.EbookAccess:
        return max(
            (e.ebook_access for e in self._solr_editions),
            default=bp.EbookAccess.NO_EBOOK,
        )

    @property
    def has_fulltext(self) -> bool:
        return any(e.has_fulltext for e in self._solr_editions)

    @property
    def public_scan_b(self) -> bool:
        return any(e.public_scan_b for e in self._solr_editions)

    @cached_property
    def ia(self) -> list[str]:
        return [cast(str, e.ia) for e in self._ia_editions]

    @property
    def ia_collection(self) -> list[str]:
        return sorted(uniq(c for e in self._solr_editions for c in e.ia_collection))

    @property
    def ia_collection_s(self) -> str:
        return ';'.join(self.ia_collection)

    @cached_property
    def _ia_editions(self) -> list[EditionSolrBuilder]:
        def get_ia_sorting_key(ed: EditionSolrBuilder) -> tuple[int, str]:
            return (
                # -1 to sort in reverse and make public first
                -1 * ed.ebook_access.value,
                # De-prioritize google scans because they are lower quality
                '0: non-goog' if not cast(str, ed.ia).endswith('goog') else '1: goog',
            )

        return sorted((e for e in self._solr_editions if e.ia), key=get_ia_sorting_key)

    # --- These should be deprecated and removed ---
    @property
    def lending_edition_s(self) -> str | None:
        if (
            not self._ia_editions
            or self._ia_editions[0].ebook_access <= bp.EbookAccess.PRINTDISABLED
        ):
            return None
        else:
            return extract_edition_olid(self._ia_editions[0].key)

    @property
    def lending_identifier_s(self) -> str | None:
        if (
            not self._ia_editions
            or self._ia_editions[0].ebook_access <= bp.EbookAccess.PRINTDISABLED
        ):
            return None
        else:
            return self._ia_editions[0].ia

    @property
    def printdisabled_s(self) -> str | None:
        printdisabled_eds = [
            ed for ed in self._ia_editions if 'printdisabled' in ed.ia_collection
        ]
        if not printdisabled_eds:
            return None
        else:
            return ';'.join(
                cast(str, extract_edition_olid(ed.key)) for ed in printdisabled_eds
            )

    # ^^^ These should be deprecated and removed ^^^

    def build_ratings(self) -> WorkRatingsSummary | None:
        return self._data_provider.get_work_ratings(self._work['key'])

    def build_reading_log(self) -> WorkReadingLogSolrSummary | None:
        return self._data_provider.get_work_reading_log(self._work['key'])

    @cached_property
    def cover_i(self) -> int | None:
        work_cover_id = next(
            itertools.chain(
                (
                    cover_id
                    for cover_id in self._work.get('covers', [])
                    if cover_id != -1
                ),
                [None],
            )
        )

        return work_cover_id or next(
            (ed.cover_i for ed in self._solr_editions if ed.cover_i is not None), None
        )

    @property
    def cover_edition_key(self) -> str | None:
        if self.cover_i is None:
            return None
        return next(
            (
                extract_edition_olid(ed['key'])
                for ed in self._editions
                if self.cover_i in ed.get('covers', [])
            ),
            None,
        )

    @property
    def first_sentence(self) -> set[str]:
        return {
            s['value'] if isinstance(s, dict) else s
            for ed in self._editions
            if (s := ed.get('first_sentence', None))
        }

    @property
    def publisher(self) -> set[str]:
        return {publisher for ed in self._solr_editions for publisher in ed.publisher}

    @property
    def format(self) -> set[str]:
        return {ed.format for ed in self._solr_editions if ed.format}

    @property
    def language(self) -> set[str]:
        return {lang for ed in self._solr_editions for lang in ed.language}

    def build_legacy_ia_fields(self) -> dict:
        ia_loaded_id = set()
        ia_box_id = set()

        for e in self._editions:
            # When do we write these to the actual edition?? This code might
            # be dead.
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

        doc = {}

        if ia_loaded_id:
            doc['ia_loaded_id'] = list(ia_loaded_id)
        if ia_box_id:
            doc['ia_box_id'] = list(ia_box_id)
        return doc

    @cached_property
    def author_key(self) -> list[str]:
        return [
            m.group(1)
            for m in (re_author_key.match(a['key']) for a in self._authors)
            if m
        ]

    @cached_property
    def author_name(self) -> list[str]:
        return [a.get('name', '') for a in self._authors]

    @cached_property
    def author_alternative_name(self) -> set[str]:
        return {
            alt_name for a in self._authors for alt_name in a.get('alternate_names', [])
        }

    @cached_property
    def author_facet(self) -> list[str]:
        return [f'{key} {name}' for key, name in zip(self.author_key, self.author_name)]

    def build_identifiers(self) -> dict[str, list[str]]:
        identifiers: dict[str, list[str]] = defaultdict(list)
        for ed in self._solr_editions:
            for k, v in ed.identifiers.items():
                identifiers[k] += v
        return dict(identifiers)

    def build_subjects(self) -> dict:
        doc: dict = {}
        field_map = {
            'subjects': 'subject',
            'subject_places': 'place',
            'subject_times': 'time',
            'subject_people': 'person',
        }
        for work_field, subject_type in field_map.items():
            if not self._work.get(work_field):
                continue

            doc |= {
                subject_type: self._work[work_field],
                f'{subject_type}_facet': self._work[work_field],
                f'{subject_type}_key': [str_to_key(s) for s in self._work[work_field]],
            }
        return doc


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
