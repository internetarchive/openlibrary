"""Module to load books into Open Library.

This is used to load books from various MARC sources, including
Internet Archive.

For loading a book, the available metadata is compiled as a dict,
called a record internally. Here is a sample record:

    {
        "title": "The Adventures of Tom Sawyer",
        "source_records": ["ia:TheAdventuresOfTomSawyer_201303"],
        "authors": [{
            "name": "Mark Twain"
        }]
    }

The title and source_records fields are mandatory.

A record is loaded by calling the load function.

    record = {...}
    response = load(record)

"""

import itertools
import logging
import re
import uuid
from collections import defaultdict
from collections.abc import Iterable
from copy import copy
from time import sleep
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlparse

import requests
import web

from infogami import config
from openlibrary import accounts
from openlibrary.catalog.add_book.load_book import (
    author_import_record_to_author,
    east_in_by_statement,
    import_record_to_edition,
)
from openlibrary.catalog.add_book.match import editions_match, mk_norm
from openlibrary.catalog.utils import (
    EARLIEST_PUBLISH_YEAR_FOR_BOOKSELLERS,
    InvalidLanguage,
    format_languages,
    get_non_isbn_asin,
    get_publication_year,
    is_independently_published,
    is_promise_item,
    needs_isbn_and_lacks_one,
    publication_too_old_and_not_exempt,
    published_in_future_year,
)
from openlibrary.core import lending
from openlibrary.plugins.upstream.utils import safeget, setup_requests, strip_accents
from openlibrary.utils import dicthash, uniq
from openlibrary.utils.isbn import normalize_isbn
from openlibrary.utils.lccn import normalize_lccn

if TYPE_CHECKING:
    from openlibrary.plugins.upstream.models import Edition

logger = logging.getLogger("add_book")

re_normalize = re.compile('[^[:alphanum:] ]', re.UNICODE)
re_lang = re.compile('^/languages/([a-z]{3})$')
ISBD_UNIT_PUNCT = ' : '  # ISBD cataloging title-unit separator punctuation
SUSPECT_PUBLICATION_DATES: Final = [
    "1900",
    "January 1, 1900",
    "1900-01-01",
    "????",
    "01-01-1900",
]
SUSPECT_DATE_EXEMPT_SOURCES: Final = ["wikisource"]
SUSPECT_AUTHOR_NAMES: Final = ["unknown", "n/a"]
SOURCE_RECORDS_REQUIRING_DATE_SCRUTINY: Final = ["amazon", "bwb", "promise"]
ALLOWED_COVER_HOSTS: Final = (
    "books.google.com",
    "commons.wikimedia.org",
    "m.media-amazon.com",
)


type_map = {
    'description': 'text',
    'notes': 'text',
    'number_of_pages': 'int',
}


class CoverNotSaved(Exception):
    def __init__(self, f):
        self.f = f

    def __str__(self):
        return f"coverstore responded with: '{self.f}'"


class RequiredFields(Exception):
    def __init__(self, fields: Iterable[str]):
        self.fields = fields

    def __str__(self):
        return f"missing required field(s): {self.fields}"


class PublicationYearTooOld(Exception):
    def __init__(self, year):
        self.year = year

    def __str__(self):
        return f"publication year is too old (i.e. earlier than {EARLIEST_PUBLISH_YEAR_FOR_BOOKSELLERS}): {self.year}"


class PublishedInFutureYear(Exception):
    def __init__(self, year):
        self.year = year

    def __str__(self):
        return f"published in future year: {self.year}"


class IndependentlyPublished(Exception):
    def __init__(self):
        pass

    def __str__(self):
        return "book is independently published"


class SourceNeedsISBN(Exception):
    def __init__(self):
        pass

    def __str__(self):
        return "this source needs an ISBN"


subject_fields = ['subjects', 'subject_places', 'subject_times', 'subject_people']


def normalize(s: str) -> str:
    """Strip non-alphanums and truncate at 25 chars."""
    norm = strip_accents(s).lower()
    norm = norm.replace(' and ', ' ')
    if norm.startswith('the '):
        norm = norm[4:]
    elif norm.startswith('a '):
        norm = norm[2:]
    # strip bracketed text
    norm = re.sub(r' ?\(.*\)', '', norm)
    return norm.replace(' ', '')[:25]


def is_redirect(thing):
    """
    :param Thing thing:
    :rtype: bool
    """
    if not thing:
        return False
    return thing.type.key == '/type/redirect'


def split_subtitle(full_title: str):
    """
    Splits a title into (title, subtitle),
    strips parenthetical tags. Used for bookseller
    catalogs which do not pre-separate subtitles.

    :param str full_title:
    :rtype: (str, str | None)
    :return: (title, subtitle | None)
    """

    # strip parenthetical blocks wherever they occur
    # can handle 1 level of nesting
    re_parens_strip = re.compile(r'\(([^\)\(]*|[^\(]*\([^\)]*\)[^\)]*)\)')
    clean_title = re.sub(re_parens_strip, '', full_title)

    titles = clean_title.split(':')
    subtitle = titles.pop().strip() if len(titles) > 1 else None
    title = ISBD_UNIT_PUNCT.join([unit.strip() for unit in titles])
    return (title, subtitle)


def find_matching_work(e):
    """
    Looks for an existing Work representing the new import edition by
    comparing normalized titles for every work by each author of the current edition.
    Returns the first match found, or None.

    :param dict e: An OL edition suitable for saving, has a key, and has full Authors with keys
                   but has not yet been saved.
    :rtype: None or str
    :return: the matched work key "/works/OL..W" if found
    """
    seen = set()
    for a in e['authors']:
        q = {'type': '/type/work', 'authors': {'author': {'key': a['key']}}}
        work_keys = list(web.ctx.site.things(q))
        for wkey in work_keys:
            w = web.ctx.site.get(wkey)
            if wkey in seen:
                continue
            seen.add(wkey)
            if not w.get('title'):
                continue
            if mk_norm(w['title']) == mk_norm(e['title']):
                assert w.type.key == '/type/work'
                return wkey


def load_author_import_records(authors_in, edits, source, save: bool = True):
    """
    Steps through an import record's authors, and creates new records if new,
    adding them to 'edits' to be saved later.

    :param list authors_in: import author dicts [{"name:" "Bob"}, ...], maybe dates
    :param list edits: list of Things to be saved later. Is modified by this method.
    :param str source: Source record e.g. marc:marc_ex/part01.dat:26456929:680
    :rtype: tuple
    :return: (list, list) authors [{"key": "/author/OL..A"}, ...], author_reply
    """
    authors = []
    author_reply = []
    for a in authors_in:
        new_author = 'key' not in a
        if new_author:
            if save:
                a['key'] = web.ctx.site.new_key('/type/author')
            else:
                a['key'] = f'/authors/__new__{uuid.uuid4()}'
            a['source_records'] = [source]
            edits.append(a)
        authors.append({'key': a['key']})
        author_reply.append(
            {
                'key': a['key'],
                'name': a['name'],
                'status': ('created' if new_author else 'matched'),
            }
        )
    return (authors, author_reply)


def new_work(
    edition: dict, rec: dict, cover_id: int | None = None, save: bool = True
) -> dict:
    """
    :param edition: New OL Edition
    :param rec: Edition import data
    :return: a work to save
    """
    w = {
        'type': {'key': '/type/work'},
        'title': rec['title'],
    }
    for s in subject_fields:
        if s in rec:
            w[s] = rec[s]

    if 'authors' in edition:
        w['authors'] = []
        assert len(edition['authors']) == len(rec['authors']), "Author import failed!"
        for i, akey in enumerate(edition['authors']):
            author = {'type': {'key': '/type/author_role'}, 'author': akey}
            if role := rec['authors'][i].get('role'):
                author['role'] = role
            w['authors'].append(author)

    if 'description' in rec:
        w['description'] = {'type': '/type/text', 'value': rec['description']}

    if save:
        w['key'] = web.ctx.site.new_key('/type/work')
    else:
        w['key'] = f'/works/__new__{uuid.uuid4()}'

    if edition.get('covers'):
        w['covers'] = edition['covers']

    return w


def add_cover(cover_url, ekey, account_key=None):
    """
    Adds a cover to coverstore and returns the cover id.

    :param str cover_url: URL of cover image
    :param str ekey: Edition key /book/OL..M
    :rtype: int or None
    :return: Cover id, or None if upload did not succeed
    """
    olid = ekey.split('/')[-1]
    coverstore_url = config.get('coverstore_url').rstrip('/')
    upload_url = coverstore_url + '/b/upload2'
    if upload_url.startswith('//'):
        upload_url = '{}:{}'.format(web.ctx.get('protocol', 'http'), upload_url)
    if not account_key:
        user = accounts.get_current_user()
        if not user:
            raise RuntimeError("accounts.get_current_user() failed")
        account_key = user.get('key') or user.get('_key')
    params = {
        'author': account_key,
        'data': None,
        'source_url': cover_url,
        'olid': olid,
        'ip': web.ctx.ip,
    }
    reply = None
    for _ in range(10):
        try:
            response = requests.post(upload_url, data=params)
        except requests.HTTPError:
            sleep(2)
            continue
        body = response.text
        if response.status_code == 500:
            raise CoverNotSaved(body)
        if body not in ['', 'None']:
            reply = response.json()
            if response.status_code == 200 and 'id' in reply:
                break
        sleep(2)
    if not reply or reply.get('message') == 'Invalid URL':
        return
    cover_id = int(reply['id'])
    return cover_id


def get_ia_item(ocaid):
    import internetarchive as ia  # noqa: PLC0415

    cfg = {'general': {'secure': False}}
    item = ia.get_item(ocaid, config=cfg)
    return item


def modify_ia_item(item, data):
    access_key = (
        lending.config_ia_ol_metadata_write_s3
        and lending.config_ia_ol_metadata_write_s3['s3_key']
    )
    secret_key = (
        lending.config_ia_ol_metadata_write_s3
        and lending.config_ia_ol_metadata_write_s3['s3_secret']
    )
    return item.modify_metadata(data, access_key=access_key, secret_key=secret_key)


def create_ol_subjects_for_ocaid(ocaid, subjects):
    item = get_ia_item(ocaid)
    openlibrary_subjects = copy(item.metadata.get('openlibrary_subject')) or []

    if not isinstance(openlibrary_subjects, list):
        openlibrary_subjects = [openlibrary_subjects]

    for subject in subjects:
        if subject not in openlibrary_subjects:
            openlibrary_subjects.append(subject)

    r = modify_ia_item(item, {'openlibrary_subject': openlibrary_subjects})
    if r.status_code != 200:
        return f'{item.identifier} failed: {r.content}'
    else:
        return f"success for {item.identifier}"


def update_ia_metadata_for_ol_edition(edition_id):
    """
    Writes the Open Library Edition and Work id to a linked
    archive.org item.

    :param str edition_id: of the form OL..M
    :rtype: dict
    :return: error report, or modified archive.org metadata on success
    """

    data = {'error': 'No qualifying edition'}
    if edition_id:
        ed = web.ctx.site.get(f'/books/{edition_id}')
        if ed.ocaid:
            work = ed.works[0] if ed.get('works') else None
            if work and work.key:
                item = get_ia_item(ed.ocaid)
                work_id = work.key.split('/')[2]
                r = modify_ia_item(
                    item,
                    {'openlibrary_work': work_id, 'openlibrary_edition': edition_id},
                )
                if r.status_code != 200:
                    data = {'error': f'{item.identifier} failed: {r.content}'}
                else:
                    data = item.metadata
    return data


def normalize_record_bibids(rec: dict):
    """
    Returns the Edition import record with all ISBN fields and LCCNs cleaned.

    :param dict rec: Edition import record
    :rtype: dict
    :return: A record with cleaned LCCNs, and ISBNs in the various possible ISBN locations.
    """
    for field in ('isbn_13', 'isbn_10', 'isbn'):
        if rec.get(field):
            rec[field] = [
                normalize_isbn(isbn)
                for isbn in rec.get(field, '')
                if normalize_isbn(isbn)
            ]
    if rec.get('lccn'):
        rec['lccn'] = [
            normalize_lccn(lccn) for lccn in rec.get('lccn', '') if normalize_lccn(lccn)
        ]
    return rec


def isbns_from_record(rec: dict) -> list[str]:
    """
    Returns a list of all isbns from the various possible isbn fields.

    :param dict rec: Edition import record
    :rtype: list
    """
    isbns = rec.get('isbn', []) + rec.get('isbn_10', []) + rec.get('isbn_13', [])
    return isbns


def find_wikisource_src(rec: dict) -> str | None:
    if not rec.get('source_records'):
        return None
    ws_prefix = 'wikisource:'
    ws_match = next(
        (src for src in rec['source_records'] if src.startswith(ws_prefix)), None
    )
    if ws_match:
        return ws_match[len(ws_prefix) :]
    return None


def build_pool(rec: dict) -> dict[str, list[str]]:
    """
    Searches for existing edition matches on title and bibliographic keys.

    :param dict rec: Edition record
    :rtype: dict
    :return: {<identifier: title | isbn | lccn etc>: [list of /books/OL..M keys that match rec on <identifier>]}
    """
    pool = defaultdict(set)
    match_fields = ('title', 'oclc_numbers', 'lccn', 'ocaid')

    if ws_match := find_wikisource_src(rec):
        # If this is a wikisource import, ONLY consider a match if the same wikisource ID
        ekeys = set(editions_matched(rec, 'identifiers.wikisource', ws_match))
        if ekeys:
            pool['wikisource'] = ekeys
        return {k: list(v) for k, v in pool.items() if v}

    # Find records with matching fields
    for field in match_fields:
        pool[field] = set(editions_matched(rec, field))

    # update title pool with normalized title matches
    pool['title'].update(
        set(editions_matched(rec, 'normalized_title_', normalize(rec['title'])))
    )

    # Find records with matching ISBNs
    if isbns := isbns_from_record(rec):
        pool['isbn'] = set(editions_matched(rec, 'isbn_', isbns))
    return {k: list(v) for k, v in pool.items() if v}


def find_quick_match(rec: dict) -> str | None:
    """
    Attempts to quickly find an existing item match using bibliographic keys.

    :param dict rec: Edition record
    :return: First key matched of format "/books/OL..M" or None if no match found.
    """
    if 'openlibrary' in rec:
        return '/books/' + rec['openlibrary']

    if ws_match := find_wikisource_src(rec):
        # If this is a wikisource import, ONLY consider a match if the same wikisource ID
        ekeys = editions_matched(rec, 'identifiers.wikisource', ws_match)
        if ekeys:
            return ekeys[0]
        else:
            return None

    ekeys = editions_matched(rec, 'ocaid')
    if ekeys:
        return ekeys[0]

    if isbns := isbns_from_record(rec):
        ekeys = editions_matched(rec, 'isbn_', isbns)
        if ekeys:
            return ekeys[0]

    # Look for a matching non-ISBN ASIN identifier (e.g. from a BWB promise item).
    if (non_isbn_asin := get_non_isbn_asin(rec)) and (
        ekeys := editions_matched(rec, "identifiers.amazon", non_isbn_asin)
    ):
        return ekeys[0]

    # Only searches for the first value from these lists
    for f in 'source_records', 'oclc_numbers', 'lccn':
        if rec.get(f):
            if f == 'source_records' and not rec[f][0].startswith('ia:'):
                continue
            if ekeys := editions_matched(rec, f, rec[f][0]):
                return ekeys[0]
    return None


def editions_matched(rec: dict, key: str, value=None) -> list[str]:
    """
    Search OL for editions matching record's 'key' value.

    :param dict rec: Edition import record
    :param str key: Key to search on, e.g. 'isbn_'
    :param list|str value: Value or Values to use, overriding record values
    :rtype: list
    :return: List of edition keys ["/books/OL..M",]
    """
    if value is None and key not in rec:
        return []

    if value is None:
        value = rec[key]

    q = {'type': '/type/edition', key: value}

    ekeys = list(web.ctx.site.things(q))
    return ekeys


def find_threshold_match(rec: dict, edition_pool: dict[str, list[str]]) -> str | None:
    """
    Find the best match for rec in edition_pool and return its key.
    :param dict rec: the new edition we are trying to match.
    :param dict edition_pool: edition key matches, output of build_pool(import record)
    :return: None or the edition key '/books/OL...M' of the best edition match for enriched_rec in edition_pool
    """
    seen = set()
    for edition_keys in edition_pool.values():
        for edition_key in edition_keys:
            if edition_key in seen:
                continue
            thing = None
            while not thing or is_redirect(thing):
                seen.add(edition_key)
                thing = web.ctx.site.get(edition_key)
                if thing is None:
                    break
                if is_redirect(thing):
                    edition_key = thing['location']
            if thing and editions_match(rec, thing):
                return edition_key
    return None


def check_cover_url_host(
    cover_url: str | None, allowed_cover_hosts: Iterable[str] = ALLOWED_COVER_HOSTS
) -> bool:
    if not cover_url:
        return False

    parsed_url = urlparse(url=cover_url)

    host_is_allowed = parsed_url.netloc.casefold() in (
        host.casefold() for host in allowed_cover_hosts
    )

    if not host_is_allowed:
        logger.info(f"disallowed cover url: {cover_url}")
        return False

    return True


def load_data(  # noqa: PLR0912, PLR0915
    rec: dict,
    account_key: str | None = None,
    existing_edition: "Edition | None" = None,
    save: bool = True,
):
    """
    Adds a new Edition to Open Library, or overwrites existing_edition with rec data.

    The overwrite option exists for cases where the existing edition data
    should be (nearly) completely overwritten by rec data. Revision 1 promise
    items are an example.

    Checks for existing Works.
    Creates a new Work, and Author, if required,
    otherwise associates the new Edition with the existing Work.

    :param dict rec: Edition record to add (no further checks at this point)
    :rtype: dict
    :return:
        {
            "success": False,
            "error": <error msg>
        }
      OR
        {
            "success": True,
            "work": {"key": <key>, "status": "created" | "modified" | "matched"},
            "edition": {"key": <key>, "status": "created"},
            "authors": [{"status": "matched", "name": "John Smith", "key": <key>}, ...]
        }
    """

    try:
        # get an OL style edition dict
        rec_as_edition = import_record_to_edition(rec)
        edition: dict[str, Any]
        if existing_edition:
            # Note: This will overwrite any fields in the existing edition. This is ok for
            # now, because we'll really only come here when overwriting a promise
            # item
            edition = existing_edition.dict() | rec_as_edition

            # Preserve source_records to avoid data loss.
            edition['source_records'] = existing_edition.get(
                'source_records', []
            ) + rec.get('source_records', [])

            # Preserve existing authors, if any.
            if authors := existing_edition.get('authors'):
                edition['authors'] = authors

        else:
            edition = rec_as_edition

    except InvalidLanguage as e:
        return {
            'success': False,
            'error': str(e),
        }

    edition_key = edition.get('key')
    if not edition_key:
        if save:
            edition_key = web.ctx.site.new_key('/type/edition')
        else:
            edition_key = f'/books/__new__{uuid.uuid4()}'

    cover_url = edition.pop("cover", None)
    if not check_cover_url_host(cover_url):
        cover_url = None

    cover_id = None
    if cover_url:
        if save:
            cover_id = add_cover(cover_url, edition_key, account_key=account_key)
        else:
            # Something to indicate that it will exist if we're just previewing.
            # Must be a number for downstream code to work
            cover_id = -2

    if cover_id:
        edition['covers'] = [cover_id]

    edits: list[dict] = []  # Things (Edition, Work, Authors) to be saved
    reply: dict = {}
    if not save:
        reply['preview'] = True
        reply['edits'] = edits

    # edition.authors may have passed through `author_import_record_to_author` in `build_query`,
    # but not necessarily
    author_in = [
        (
            author_import_record_to_author(a, eastern=east_in_by_statement(rec, a))
            if isinstance(a, dict)
            else a
        )
        for a in edition.get('authors', [])
    ]
    # build_author_reply() adds authors to edits
    (authors, author_reply) = load_author_import_records(
        author_in, edits, rec['source_records'][0], save=save
    )

    if authors:
        edition['authors'] = authors
        reply['authors'] = author_reply

    work_key = safeget(lambda: edition['works'][0]['key'])
    work_state = 'created'
    # Look for an existing work
    if not work_key and 'authors' in edition:
        work_key = find_matching_work(edition)
    if work_key:
        work = web.ctx.site.get(work_key)
        work_state = 'matched'
        need_update = False
        for k in subject_fields:
            if k not in rec:
                continue
            for s in rec[k]:
                if normalize(s) not in [
                    normalize(existing) for existing in work.get(k, [])
                ]:
                    work.setdefault(k, []).append(s)
                    need_update = True
        if cover_id:
            work.setdefault('covers', []).append(cover_id)
            need_update = True
        if need_update:
            work_state = 'modified'
            edits.append(work.dict())
    else:
        # Create new work
        work = new_work(edition, rec, cover_id, save=save)
        work_state = 'created'
        work_key = work['key']
        edits.append(work)

    assert work_key
    if not edition.get('works'):
        edition['works'] = [{'key': work_key}]
    edition['key'] = edition_key
    edits.append(edition)

    if save:
        comment = (
            "overwrite existing edition" if existing_edition else "import new book"
        )
        web.ctx.site.save_many(edits, comment=comment, action='add-book')

        # Writes back `openlibrary_edition` and `openlibrary_work` to
        # archive.org item after successful import:
        if 'ocaid' in rec:
            update_ia_metadata_for_ol_edition(edition_key.split('/')[-1])

    reply['success'] = True
    reply['edition'] = (
        {'key': edition_key, 'status': 'modified'}
        if existing_edition
        else {'key': edition_key, 'status': 'created'}
    )
    reply['work'] = {'key': work_key, 'status': work_state}
    return reply


def normalize_import_record(rec: dict) -> None:
    """
    Normalize the import record by:
        - Verifying required fields;
        - Ensuring source_records is a list;
        - Splitting subtitles out of the title field;
        - Cleaning all ISBN and LCCN fields ('bibids');
        - Deduplicate authors; and
        - Remove throw-away data used for validation.
        - Remove publication years of 1900 for AMZ/BWB/Promise.

        NOTE: This function modifies the passed-in rec in place.
    """
    required_fields = {
        'title',
        'source_records',
    }  # ['authors', 'publishers', 'publish_date']
    if missing_required_fields := required_fields - rec.keys():
        raise RequiredFields(missing_required_fields)

    # Ensure source_records is a list.
    if not isinstance(rec['source_records'], list):
        rec['source_records'] = [rec['source_records']]

    publication_year = get_publication_year(rec.get('publish_date'))
    if publication_year and published_in_future_year(publication_year):
        del rec['publish_date']

    # Split subtitle if required and not already present
    if ':' in rec.get('title', '') and not rec.get('subtitle'):
        title, subtitle = split_subtitle(rec.get('title', ''))
        if subtitle:
            rec['title'] = title
            rec['subtitle'] = subtitle

    rec = normalize_record_bibids(rec)

    # deduplicate authors
    rec['authors'] = uniq(rec.get('authors', []), dicthash)

    # Validation by parse_data(), prior to calling load(), requires facially
    # valid publishers. If data are unavailable, we provide throw-away data
    # which validates. We use ["????"] as an override, but this must be
    # removed prior to import.
    if rec.get('publishers') == ["????"]:
        rec.pop('publishers')

    # Remove suspect publication dates from certain sources (e.g. 1900 from Amazon).
    if any(
        source_record.split(":")[0] in SOURCE_RECORDS_REQUIRING_DATE_SCRUTINY
        and rec.get('publish_date') in SUSPECT_PUBLICATION_DATES
        for source_record in rec['source_records']
    ):
        rec.pop('publish_date')


def validate_record(rec: dict) -> None:
    """
    Check for:
        - publication years too old from non-exempt sources (e.g. Amazon);
        - publish dates in a future year;
        - independently published books; and
        - books that need an ISBN and lack one.

    Each check raises an error or returns None.

    If all the validations pass, implicitly return None.
    """
    source_records = rec.get('source_records', [])
    source_records = (
        source_records if isinstance(source_records, list) else [source_records]
    )

    if any(rec.startswith('ia:') for rec in source_records):
        return None

    # Only validate publication year if a year is found.
    if publication_year := get_publication_year(rec.get('publish_date')):
        if publication_too_old_and_not_exempt(rec):
            raise PublicationYearTooOld(publication_year)
        elif published_in_future_year(publication_year):
            raise PublishedInFutureYear(publication_year)

    if is_independently_published(rec.get('publishers', [])):
        raise IndependentlyPublished

    if needs_isbn_and_lacks_one(rec):
        raise SourceNeedsISBN


def find_match(rec: dict, edition_pool: dict) -> str | None:
    """Use rec to try to find an existing edition key that matches."""
    return find_quick_match(rec) or find_threshold_match(rec, edition_pool)


def update_edition_with_rec_data(
    rec: dict, account_key: str | None, edition: "Edition", save: bool
) -> bool:
    """
    Enrich the Edition by adding certain fields present in rec but absent
    in edition.

    NOTE: This modifies the passed-in Edition in place.
    """
    need_edition_save = False
    # Add cover to edition
    if 'cover' in rec and not edition.get_covers():
        cover_url = rec['cover']
        if save:
            cover_id = add_cover(cover_url, edition.key, account_key=account_key)
        else:
            # Something to indicate that it will exist if we're just previewing
            # Must be a number for downstream code to work
            cover_id = -2

        if cover_id:
            edition['covers'] = [cover_id]
            need_edition_save = True

    # Add ocaid to edition (str), if needed
    if 'ocaid' in rec and not edition.ocaid:
        edition['ocaid'] = rec['ocaid']
        need_edition_save = True

    # Fields which have their VALUES added if absent.
    edition_list_fields = [
        'local_id',
        'lccn',
        'lc_classifications',
        'oclc_numbers',
        'source_records',
        'languages',
    ]
    edition_dict: dict = edition.dict()
    for field in edition_list_fields:
        if field not in rec:
            continue

        existing_values = edition_dict.get(field, []) or []
        rec_values = rec.get(field, [])

        # Languages in `rec` are ['eng'], etc., but import requires dict-style.
        if field == 'languages':
            formatted_languages = format_languages(languages=rec_values)
            supplemented_values = existing_values + [
                lang for lang in formatted_languages if lang not in existing_values
            ]
        else:
            case_folded_values = [v.casefold() for v in existing_values]
            supplemented_values = existing_values + [
                v for v in rec_values if v.casefold() not in case_folded_values
            ]

        if existing_values != supplemented_values:
            edition[field] = supplemented_values
            need_edition_save = True

    # Fields that are added as a whole if absent. (Individual values are not added.)
    other_edition_fields = [
        'description',
        'number_of_pages',
        'publishers',
        'publish_date',
    ]
    for f in other_edition_fields:
        if f not in rec or not rec[f]:
            continue
        if f not in edition:
            edition[f] = rec[f]
            need_edition_save = True

    # Add new identifiers (dict values, so different treatment from lists above.)
    if 'identifiers' in rec:
        identifiers = defaultdict(list, edition.dict().get('identifiers', {}))
        for k, vals in rec['identifiers'].items():
            identifiers[k].extend(vals)
            identifiers[k] = list(set(identifiers[k]))
        if edition.dict().get('identifiers') != identifiers:
            edition['identifiers'] = identifiers
            need_edition_save = True

    return need_edition_save


def update_work_with_rec_data(
    rec: dict, edition: "Edition", work: dict[str, Any], need_work_save: bool
) -> bool:
    """
    Enrich the Work by adding certain fields present in rec but absent
    in work.

    NOTE: This modifies the passed-in Work in place.
    """
    # Add subjects to work, if not already present
    if 'subjects' in rec:
        work_subjects: list[str] = list(work.get('subjects', []))
        rec_subjects: list[str] = rec.get('subjects', [])
        deduped_subjects = uniq(
            itertools.chain(work_subjects, rec_subjects), lambda item: item.casefold()
        )

        if work_subjects != deduped_subjects:
            work['subjects'] = deduped_subjects
            need_work_save = True

    # Add cover to work, if needed
    if not work.get('covers') and edition.get_covers():
        work['covers'] = [edition['covers'][0]]
        need_work_save = True

    # Add description to work, if needed
    if not work.get('description') and edition.get('description'):
        work['description'] = edition['description']
        need_work_save = True

    # Add authors to work, if needed
    if not work.get('authors'):
        authors = [author_import_record_to_author(a) for a in rec.get('authors', [])]
        work['authors'] = [
            {'type': {'key': '/type/author_role'}, 'author': a.get('key')}
            for a in authors
            if a.get('key')
        ]
        if work.get('authors'):
            need_work_save = True

    return need_work_save


def should_overwrite_promise_item(
    edition: "Edition", from_marc_record: bool = False
) -> bool:
    """
    Returns True for revision 1 promise items with MARC data available.

    Promise items frequently have low quality data, and MARC data is high
    quality. Overwriting revision 1 promise items with MARC data ensures
    higher quality records and eliminates the risk of obliterating human edits.
    """
    if edition.get('revision') != 1 or not from_marc_record:
        return False

    # Promise items are always index 0 in source_records.
    return bool(safeget(lambda: edition['source_records'][0], '').startswith("promise"))


def load(
    rec: dict,
    account_key=None,
    from_marc_record: bool = False,
    save: bool = True,
) -> dict:
    """Given a record, tries to add/match that edition in the system.

    Record is a dictionary containing all the metadata of the edition.
    The following fields are mandatory:

        * title: str
        * source_records: list

    :param rec: Edition record to add
    :param from_marc_record: whether the record is based on a MARC record.
    :param save: Whether to actually save
    :return: a response dict, same as load_data()
    """
    if not is_promise_item(rec):
        validate_record(rec)

    normalize_import_record(rec)

    # Resolve an edition if possible, or create and return one if not.
    edition_pool = build_pool(rec)
    if not edition_pool:
        # No match candidates found, add edition
        return load_data(rec, account_key=account_key, save=save)

    match = find_match(rec, edition_pool)
    if not match:
        # No match found, add edition
        return load_data(rec, account_key=account_key, save=save)

    # We have an edition match at this point
    need_work_save = need_edition_save = False
    work: dict[str, Any]
    existing_edition: Edition = web.ctx.site.get(match)

    # check for, and resolve, author redirects
    for a in existing_edition.authors:
        while is_redirect(a):
            if a in existing_edition.authors:
                existing_edition.authors.remove(a)
            a = web.ctx.site.get(a.location)
            if not is_redirect(a):
                existing_edition.authors.append(a)

    if existing_edition.get('works'):
        work = existing_edition.works[0].dict()
        work_created = False
    else:
        # Found an edition without a work
        work_created = need_work_save = need_edition_save = True
        work = new_work(existing_edition.dict(), rec)
        existing_edition.works = [{'key': work['key']}]

    # Send revision 1 promise item editions to the same pipeline as new editions
    # because we want to overwrite most of their data.
    if should_overwrite_promise_item(
        edition=existing_edition, from_marc_record=from_marc_record
    ):
        return load_data(
            rec,
            account_key=account_key,
            existing_edition=existing_edition,
            save=save,
        )

    need_edition_save = update_edition_with_rec_data(
        rec=rec, account_key=account_key, edition=existing_edition, save=save
    )
    need_work_save = update_work_with_rec_data(
        rec=rec, edition=existing_edition, work=work, need_work_save=need_work_save
    )

    edits: list[dict] = []
    reply: dict = {
        'success': True,
        'edition': {'key': match, 'status': 'matched'},
        'work': {'key': work['key'], 'status': 'matched'},
    }

    if not save:
        reply['preview'] = True
        reply['edits'] = edits

    if need_edition_save:
        reply['edition']['status'] = 'modified'  # type: ignore[index]
        edits.append(existing_edition.dict())
    if need_work_save:
        reply['work']['status'] = 'created' if work_created else 'modified'  # type: ignore[index]
        edits.append(work)

    if save:
        if edits:
            web.ctx.site.save_many(
                edits, comment='import existing book', action='edit-book'
            )
        if 'ocaid' in rec:
            update_ia_metadata_for_ol_edition(match.split('/')[-1])

    return reply


def setup():
    setup_requests()


setup()
