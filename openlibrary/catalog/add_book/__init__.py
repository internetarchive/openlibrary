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
from __future__ import annotations
import json
import re

import web

from collections import defaultdict
from copy import copy
from time import sleep
from typing import cast, Final, TYPE_CHECKING

import requests

from infogami import config

from openlibrary import accounts
from openlibrary.catalog.merge.merge_marc import build_marc
from openlibrary.catalog.utils import mk_norm
from openlibrary.core import lending
from openlibrary.plugins.upstream.utils import strip_accents
from openlibrary.utils import uniq, dicthash
from openlibrary.utils.isbn import normalize_isbn
from openlibrary.utils.lccn import normalize_lccn

from openlibrary.catalog.add_book.load_book import (
    build_query,
    east_in_by_statement,
    import_author,
    IncomingEdition,
    InvalidLanguage,
)
from openlibrary.catalog.add_book.match import editions_match

if TYPE_CHECKING:
    from openlibrary.plugins.upstream.models import Edition, Work


re_normalize = re.compile('[^[:alphanum:] ]', re.U)
re_lang = re.compile('^/languages/([a-z]{3})$')
ISBD_UNIT_PUNCT = ' : '  # ISBD cataloging title-unit separator punctuation


class CoverNotSaved(Exception):
    def __init__(self, f):
        self.f = f

    def __str__(self):
        return "coverstore responded with: '%s'" % self.f


class RequiredField(Exception):
    def __init__(self, f):
        self.f = f

    def __str__(self):
        return "missing required field: %s" % self.f


# don't use any of these as work titles
bad_titles = {
    'Publications',
    'Works. English',
    'Missal',
    'Works',
    'Report',
    'Letters',
    'Calendar',
    'Bulletin',
    'Plays',
    'Sermons',
    'Correspondence',
    'Bill',
    'Bills',
    'Selections',
    'Selected works',
    'Selected works. English',
    'The Novels',
    'Laws, etc',
}

subject_fields = ['subjects', 'subject_places', 'subject_times', 'subject_people']


def normalize(s):
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


def get_title(e):
    if not e.get('work_titles'):
        return e['title']
    wt = e['work_titles'][0]
    return e['title'] if wt in bad_titles else e['title']


def split_subtitle(full_title):
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

    norm_title = mk_norm(get_title(e))
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
            if mk_norm(w['title']) == norm_title:
                assert w.type.key == '/type/work'
                return wkey


def build_author_reply(authors_in, edits, source):
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
            a['key'] = web.ctx.site.new_key('/type/author')
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


def new_work(edition, rec, cover_id=None):
    """
    :param dict edition: New OL Edition
    :param dict rec: Edition import data
    :param (int|None) cover_id: cover id
    :rtype: dict
    :return: a work to save
    """
    w = {
        'type': {'key': '/type/work'},
        'title': get_title(rec),
    }
    for s in subject_fields:
        if s in rec:
            w[s] = rec[s]

    if 'authors' in edition:
        w['authors'] = [
            {'type': {'key': '/type/author_role'}, 'author': akey}
            for akey in edition['authors']
        ]

    if 'description' in rec:
        w['description'] = {'type': '/type/text', 'value': rec['description']}

    wkey = web.ctx.site.new_key('/type/work')
    if edition.get('covers'):
        w['covers'] = edition['covers']
    w['key'] = wkey
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
    for attempt in range(10):
        try:
            payload = requests.compat.urlencode(params).encode('utf-8')
            response = requests.post(upload_url, data=payload)
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
    import internetarchive as ia

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
        return "success for %s" % item.identifier


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
        ed = web.ctx.site.get('/books/%s' % edition_id)
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


def normalize_record_bibids(rec):
    """
    Returns the Edition import record with all ISBN fields and LCCNs cleaned.

    :param dict rec: Edition import record
    :rtype: dict
    :return: A record with cleaned LCCNs, and ISBNs in the various possible ISBN locations.
    """
    for field in ('isbn_13', 'isbn_10', 'isbn'):
        if rec.get(field):
            rec[field] = [
                normalize_isbn(isbn) for isbn in rec.get(field) if normalize_isbn(isbn)
            ]
    if rec.get('lccn'):
        rec['lccn'] = [
            normalize_lccn(lccn) for lccn in rec.get('lccn') if normalize_lccn(lccn)
        ]
    return rec


def isbns_from_record(rec):
    """
    Returns a list of all isbns from the various possible isbn fields.

    :param dict rec: Edition import record
    :rtype: list
    """
    isbns = rec.get('isbn', []) + rec.get('isbn_10', []) + rec.get('isbn_13', [])
    return isbns


def build_pool(rec):
    """
    Searches for existing edition matches on title and bibliographic keys.

    :param dict rec: Edition record
    :rtype: dict
    :return: {<identifier: title | isbn | lccn etc>: [list of /books/OL..M keys that match rec on <identifier>]}
    """
    pool = defaultdict(set)
    match_fields = ('title', 'oclc_numbers', 'lccn', 'ocaid')

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


def early_exit(rec):
    """
    Attempts to quickly find an existing item match using bibliographic keys.

    :param dict rec: Edition record
    :rtype: str|bool
    :return: First key matched of format "/books/OL..M" or False if no match found.
    """

    if 'openlibrary' in rec:
        return '/books/' + rec['openlibrary']

    ekeys = editions_matched(rec, 'ocaid')
    if ekeys:
        return ekeys[0]

    if isbns := isbns_from_record(rec):
        ekeys = editions_matched(rec, 'isbn_', isbns)
        if ekeys:
            return ekeys[0]

    # only searches for the first value from these lists
    for f in 'source_records', 'oclc_numbers', 'lccn':
        if rec.get(f):
            if f == 'source_records' and not rec[f][0].startswith('ia:'):
                continue
            ekeys = editions_matched(rec, f, rec[f][0])
            if ekeys:
                return ekeys[0]
    return False


def editions_matched(rec, key, value=None):
    """
    Search OL for editions matching record's 'key' value.

    :param dict rec: Edition import record
    :param str key: Key to search on, e.g. 'isbn_'
    :param list|str value: Value or Values to use, overriding record values
    :rtpye: list
    :return: List of edition keys ["/books/OL..M",]
    """
    if value is None and key not in rec:
        return []

    if value is None:
        value = rec[key]
    q = {'type': '/type/edition', key: value}
    ekeys = list(web.ctx.site.things(q))
    return ekeys


def find_exact_match(rec, edition_pool):
    """
    Returns an edition key match for rec from edition_pool
    Only returns a key if all values match?

    :param dict rec: Edition import record
    :param dict edition_pool:
    :rtype: str|bool
    :return: edition key
    """
    seen = set()
    for field, editions in edition_pool.items():
        for ekey in editions:
            if ekey in seen:
                continue
            seen.add(ekey)
            existing = web.ctx.site.get(ekey)
            match = True
            for k, v in rec.items():
                if k == 'source_records':
                    continue
                existing_value = existing.get(k)
                if not existing_value:
                    continue
                if k == 'languages':
                    existing_value = [
                        str(re_lang.match(lang.key).group(1)) for lang in existing_value
                    ]
                if k == 'authors':
                    existing_value = [dict(a) for a in existing_value]
                    for a in existing_value:
                        del a['type']
                        del a['key']
                    for a in v:
                        if 'entity_type' in a:
                            del a['entity_type']
                        if 'db_name' in a:
                            del a['db_name']

                if existing_value != v:
                    match = False
                    break
            if match:
                return ekey
    return False


def find_match(e1, edition_pool):
    """
    Find the best match for e1 in edition_pool and return its key.
    :param dict e1: the new edition we are trying to match, output of build_marc(import record)
    :param list edition_pool: list of possible edition matches, output of build_pool(import record)
    :rtype: str|None
    :return: None or the edition key '/books/OL...M' of the best edition match for e1 in edition_pool
    """
    seen = set()
    for k, v in edition_pool.items():
        for edition_key in v:
            if edition_key in seen:
                continue
            thing = None
            found = True
            while not thing or is_redirect(thing):
                seen.add(edition_key)
                thing = web.ctx.site.get(edition_key)
                if thing is None:
                    found = False
                    break
                if is_redirect(thing):
                    edition_key = thing['location']
                    # FIXME: this updates edition_key, but leaves thing as redirect,
                    # which will raise an exception in editions_match()
            if not found:
                continue
            if editions_match(e1, thing):
                return edition_key


def add_db_name(rec):
    """
    db_name = Author name followed by dates.
    adds 'db_name' in place for each author.
    """
    if 'authors' not in rec:
        return

    for a in rec['authors']:
        date = None
        if 'date' in a:
            assert 'birth_date' not in a and 'death_date' not in a
            date = a['date']
        elif 'birth_date' in a or 'death_date' in a:
            date = a.get('birth_date', '') + '-' + a.get('death_date', '')
        a['db_name'] = ' '.join([a['name'], date]) if date else a['name']


def load_data(rec, account_key=None):
    """
    Adds a new Edition to Open Library. Checks for existing Works.
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

    cover_url = None
    if 'cover' in rec:
        cover_url = rec['cover']
        del rec['cover']
    try:
        # get an OL style edition dict
        edition = build_query(rec)
    except InvalidLanguage as e:
        return {
            'success': False,
            'error': str(e),
        }

    ekey = web.ctx.site.new_key('/type/edition')
    cover_id = None
    if cover_url:
        cover_id = add_cover(cover_url, ekey, account_key=account_key)
    if cover_id:
        edition['covers'] = [cover_id]

    edits = []  # Things (Edition, Work, Authors) to be saved
    reply = {}
    # TOFIX: edition.authors has already been processed by import_authors() in build_query(), following line is a NOP?
    author_in = [
        import_author(a, eastern=east_in_by_statement(rec, a))
        for a in edition.get('authors', [])
    ]
    # build_author_reply() adds authors to edits
    (authors, author_reply) = build_author_reply(
        author_in, edits, rec['source_records'][0]
    )

    if authors:
        edition['authors'] = authors
        reply['authors'] = author_reply

    wkey = None
    work_state = 'created'
    # Look for an existing work
    if 'authors' in edition:
        wkey = find_matching_work(edition)
    if wkey:
        w = web.ctx.site.get(wkey)
        work_state = 'matched'
        found_wkey_match = True
        need_update = False
        for k in subject_fields:
            if k not in rec:
                continue
            for s in rec[k]:
                if normalize(s) not in [
                    normalize(existing) for existing in w.get(k, [])
                ]:
                    w.setdefault(k, []).append(s)
                    need_update = True
        if cover_id:
            w.setdefault('covers', []).append(cover_id)
            need_update = True
        if need_update:
            work_state = 'modified'
            edits.append(w.dict())
    else:
        # Create new work
        w = new_work(edition, rec, cover_id)
        wkey = w['key']
        edits.append(w)

    assert wkey
    edition['works'] = [{'key': wkey}]
    edition['key'] = ekey
    edits.append(edition)

    web.ctx.site.save_many(edits, comment='import new book', action='add-book')

    # Writes back `openlibrary_edition` and `openlibrary_work` to
    # archive.org item after successful import:
    if 'ocaid' in rec:
        update_ia_metadata_for_ol_edition(ekey.split('/')[-1])

    reply['success'] = True
    reply['edition'] = {'key': ekey, 'status': 'created'}
    reply['work'] = {'key': wkey, 'status': work_state}
    return reply


def add_missing_int_and_str_to_edition(
    incoming_edition: IncomingEdition,
    matched_edition: Edition,
    overwrite: bool = False,
) -> tuple[Edition, bool]:
    """
    Add missing string-like and int-like values from incoming_edition to the matched_edition.

    :param incoming_edition: A rec dictionary returned from build_query().
    :param matched_edition: The matched target edition that will be updated with any new values.
    :param overwrite: If True, use incoming_edition values to overwrite those in matched_edition.
    :return: A tuple containing the (possibly modified) matched_edition and a bool indicating
        whether the matched_edition needs to be saved.
    """
    need_edition_save = False
    # Update `matched_edition` str and int value fields with `incoming_edition` values. Don't overwrite
    # existing fields by default.
    for field, value in incoming_edition.items():
        if field in matched_edition and overwrite is False:
            continue

        if isinstance(value, (str, int)):
            matched_edition[field] = value
            need_edition_save = True
            continue

        if isinstance(value, dict):
            if value.get('type') in ('/type/int', '/type/text'):
                matched_edition[field] = value
                need_edition_save = True
                continue

    return matched_edition, need_edition_save


# Add list fields to edition as needed.
# Fields in this list must be the same format in both `incoming_edition` and
# `matched_edition`. For example, if the `matched_edition` field value is a
# `Thing`, the fields will not match properly.
EDITION_LIST_FIELDS: Final = [
    'author',
    'dewey_decimal_class',
    'isbn_10',
    'isbn_13',
    'lc_classifications',
    'lccn',
    'local_id',
    'oclc_numbers',
    'publish_places',
    'publishers',
    'series',
    'source_records',
    'translation_of',
    'work_titles',
]


def add_missing_lists_to_edition(
    incoming_edition: IncomingEdition,
    matched_edition: Edition,
    edition_list_fields: list[str],
    overwrite: bool = False,
) -> tuple[Edition, bool]:
    """
    Add missing lists and list values from incoming_edition to the matched_edition.

    :param incoming_edition: A rec dictionary returned from build_query().
    :param matched_edition: The matched target edition that will be updated with any new values.
    :param edition_list_fields: A list of field keys (associated with list values) to copy.
    :param overwrite: If True, use incoming_edition values to overwrite those in matched_edition.
    :return: A tuple containing the (possibly modified) edition and a bool indicating
        whether the matched_edition needs to be saved.
    """
    need_edition_save = False

    for field in edition_list_fields:
        if not incoming_edition.get(field):
            continue

        # Re-write specific fields in *incoming_edition* to scrub data before (potential)
        # copying to edition.
        if field == 'publish_places':
            # Places such as "[Paris]" should be stripped.
            incoming_edition[field] = [
                place.strip("][)(") for place in incoming_edition[field]
            ]

        # There are three outcomes: write the incoming_edition data to the
        # matched_edition, append it the matched_edition, or do nothing.

        if (overwrite and field != 'source_records') or field not in matched_edition:
            matched_edition[field] = incoming_edition[field]
            need_edition_save = True
            continue

        if values_to_append := [
            value
            for value in incoming_edition[field]
            if value not in matched_edition[field]
        ]:
            matched_edition[field] += values_to_append
            need_edition_save = True

    return (matched_edition, need_edition_save)


# Key: thing-field-name. Value: key-in-thing-item-used-for-comparison.
#
# `Thing` values in `matched_edition` must be compared separately, as neither
# `rec` nor `incoming_edition` have `Thing` values.
# E.g. `incoming_edition` might have `'languages': [{'key': '/languages/fre'}]`, and `edition`
# might have `'languages': [Thing(site=<infogami.infobase.client.Site object at 0x7f9fe484f110>, key=/languages/fre, data=None, revision=None)]`,
# so we'd compare `key`, as both are `/languages/fre`.
EDITION_THING_FIELDS: Final = {
    'languages': 'key',
    'links': 'url',
    'translated_from': 'key',
}


def add_missing_things_to_edition(
    incoming_edition: IncomingEdition,
    matched_edition: Edition,
    edition_thing_fields: dict[str, str],
    overwrite: bool = False,
) -> tuple[Edition, bool]:
    """
    Add missing Things and Thing values from incoming_edition to the matched_edition.

    :param incoming_edition: A rec dictionary returned from build_query().
    :param matched_edition: The matched target edition that will be updated with any new values.
    :param edition_fields: A list of field names, themselves containing Things, to copy.
    :param overwrite: If True, use incoming_edition values to overwrite those in matched_edition.
    :return: A tuple containing the (possibly modified) edition and a bool indicating
        whether the matched_edition needs to be saved.
    """
    need_edition_save = False

    for field, thing_key in edition_thing_fields.items():
        if not incoming_edition.get(field):
            continue

        if overwrite or field not in matched_edition:
            matched_edition[field] = incoming_edition[field]
            need_edition_save = True
            continue

        # incoming_edition has a JSON-like representation of some values that are
        # Thing objects in the edition (e.g. 'languages'). Get the relevant values
        # for comparison (see the commennt to THING_EDITION_FIELDS), and then add
        # them to the edition if absent.
        #
        # We know if it's absent by comparing the relevant keys in the `Thing`
        # and the incoming_edition JSON-like representation.
        #
        # E.g. if processing the `languages` field, then per THING_EDITION_FIELDS,
        # the `thing_key` is literally `key`. That `Thing` might look like:
        # Thing(site=<infogami.infobase.client.Site object at 0x7f9fe484f110>, key=/languages/fre, data=None, revision=None).
        #
        # Having gathered all the `thing_key` values, we append anything from
        # incoming_edition that isn't the value of an existing `thing_key`.
        values_in_edition = [thing.get(thing_key) for thing in matched_edition[field]]
        if values_to_append := [
            item
            for item in incoming_edition[field]
            if item.get(thing_key) not in values_in_edition
        ]:
            matched_edition[field] += values_to_append
            need_edition_save = True

    return (matched_edition, need_edition_save)


def check_if_edition_should_be_overwritten(
    matched_edition: Edition, from_marc_record: bool
) -> bool:
    """
    Certain editions should be overwritten with incoming_edition data because
    of their pervasive low quality, such as revision 1 Promise Items.

    :param matched_edition: The edition to evaluate for overwriting.
    :param from_marc_record: True if the incoming_edition associated with this
        matched Edition has a MARC record.
    :returns: True if the matched_edition data should be overwritten.
    """
    if not from_marc_record or matched_edition.get('revision') != 1:
        return False

    # v1 Promise Items are always index[0] in source_records.
    if source_records := matched_edition.get('source_records'):
        if source_records[0].split(":")[0] == "promise":
            return True

    return False


def update_matched_edition(
    matched_edition: Edition,
    rec: dict,
    account_key: str | None = None,
    from_marc_record: bool = False,
) -> tuple[Edition, bool]:
    """
    Update `matched_edition` fields to add values from `rec` that don't
    currently exist on `matched_edition`. The default is to prefer existing
    values rather than to overwrite.

    :param matched_edition: The matched Edition to evaluate for overwriting.
    :param rec: The `rec` being imported that possibly (1) has new values
        or (2) should be used for overwriting `matched_edition`.
    :param from_marc_record: True if the `rec` has a MARC record.
    :return: A tuple containing the (possibly modified) matched_edition and
        a bool indicating whether the edition needs to be saved.
    """
    # The different update functions called here return bools that, if True,
    # mean the matched_edition should be saved. Track them for clarity.
    needs_save: dict[str, bool] = {}

    # Add cover to `matched_edition`, and remove `cover` from `rec`, because
    # it's not a valid `Edition` field and would otherwise be copied in.
    cover_url = rec.pop('cover', None)
    if cover_url and not matched_edition.get_covers():
        if cover_id := add_cover(
            cover_url, matched_edition.key, account_key=account_key
        ):
            matched_edition['covers'] = [cover_id]
            needs_save['cover'] = True

    # Convert the record to an OpenLibrary Edition suitable for saving, so
    # that values copied from the record into the Edition are of the proper
    # format.
    incoming_edition = build_query(rec)

    should_overwrite = check_if_edition_should_be_overwritten(
        matched_edition, from_marc_record
    )

    matched_edition, needs_save['int_and_str'] = add_missing_int_and_str_to_edition(
        incoming_edition, matched_edition, should_overwrite
    )

    matched_edition, needs_save['lists'] = add_missing_lists_to_edition(
        incoming_edition=incoming_edition,
        matched_edition=matched_edition,
        edition_list_fields=EDITION_LIST_FIELDS,
        overwrite=should_overwrite,
    )

    matched_edition, needs_save['things'] = add_missing_things_to_edition(
        incoming_edition=incoming_edition,
        matched_edition=matched_edition,
        edition_thing_fields=EDITION_THING_FIELDS,
        overwrite=should_overwrite,
    )

    # Add new identifiers
    if 'identifiers' in incoming_edition:
        identifiers = defaultdict(list, matched_edition.dict().get('identifiers', {}))
        for k, vals in incoming_edition['identifiers'].items():
            identifiers[k].extend(vals)
            identifiers[k] = list(set(identifiers[k]))
        if matched_edition.dict().get('identifiers') != identifiers:
            matched_edition['identifiers'] = identifiers
            need_edition_save = True

    need_edition_save = any(needs_save.values())

    return (matched_edition, need_edition_save)


def update_matched_work(work: Work, edition: Edition, rec: dict) -> tuple[Work, bool]:
    """
    Update a matched Work.

    :param work: The matched work.
    :param edition: The matched edition.
    :param rec: The incoming import record.
    :return: A tuple containing the (possibly modified) work and a bool indicating
        whether the work needs to be saved.
    """
    need_work_save = False

    # Add subjects to work, if not already present
    if 'subjects' in rec:
        work_subjects = list(work.get('subjects', []))
        for s in rec['subjects']:
            if s not in work_subjects:
                work_subjects.append(s)
                need_work_save = True
        if need_work_save and work_subjects:
            work['subjects'] = work_subjects

    # Add cover to work, if needed
    if not work.get('covers') and edition.get_covers():
        work['covers'] = [edition['covers'][0]]
        need_work_save = True

    # Add description to work, if needed
    if not work.get('description') and edition.get('description'):
        work['description'] = edition['description']
        need_work_save = True

    # Add authors to work, if needed
    if "authors" in rec and rec["authors"]:
        rec_authors = [import_author(a) for a in rec.get('authors', [])]

        # Get existing author keys
        work_author_keys: list[str | None] = [
            author.get("author", {}).get("key")
            for author in work.get("authors", [])
            if isinstance(author, dict)
        ]

        add_authors = [
            author
            for author in rec_authors
            if author.get("key") not in work_author_keys
        ]

        # Authors can only be added, so we can compare the length of the Work's
        # authors to see if we need to save.
        w_original_author_count = len(work.get("authors", []))
        work.get("authors", []).extend(
            [
                {'type': {'key': '/type/author_role'}, 'author': a.key}
                for a in add_authors
                if a.get('key')
            ]
        )

        if len(work.get("authors", [])) != w_original_author_count:
            need_work_save = True

    return (work, need_work_save)


def load(rec, account_key=None, from_marc_record: bool = False):
    """Given a record, tries to add/match an edition/work in the system.

    If rec *is* matched to an edition, fields in the rec that are
    *not present* in the edition will be added to the edition.

    If the edition is a v1 promise item, and the rec has MARC data,
    the edition will be entirely overwritten with the rec's data
    because of promise items' low quality data.

    If rec is *not* matched to an edition, it will be passed to
    load_data() so a new edition can be created.

    rec is a dictionary containing all the metadata of the edition.
    The following fields are mandatory:

        * title: str
        * source_records: list

    :param dict rec: Edition record to add
    :rtype: dict
    :return: a dict to be converted into a JSON HTTP response, same as load_data()
    """

    required_fields = [
        'title',
        'source_records',
    ]  # ['authors', 'publishers', 'publish_date']
    for field in required_fields:
        if not rec.get(field):
            raise RequiredField(field)
    if not isinstance(rec['source_records'], list):
        rec['source_records'] = [rec['source_records']]

    # Split subtitle if required and not already present
    if ':' in rec.get('title') and not rec.get('subtitle'):
        title, subtitle = split_subtitle(rec.get('title'))
        if subtitle:
            rec['title'] = title
            rec['subtitle'] = subtitle

    rec = normalize_record_bibids(rec)

    edition_pool = build_pool(rec)
    # deduplicate authors
    rec['authors'] = uniq(rec.get('authors', []), dicthash)
    if not edition_pool:
        # No match candidates found, add edition
        return load_data(rec, account_key=account_key)

    match = early_exit(rec)
    if not match:
        match = find_exact_match(rec, edition_pool)

    if not match:
        rec['full_title'] = rec['title']
        if rec.get('subtitle'):
            rec['full_title'] += ' ' + rec['subtitle']
        e1 = build_marc(rec)
        add_db_name(e1)
        match = find_match(e1, edition_pool)

    if not match:
        # No match found, add edition
        return load_data(rec, account_key=account_key)

    # We have an edition match at this point
    need_work_save = need_edition_save = False
    w = None
    e: Edition = web.ctx.site.get(match)
    # check for, and resolve, author redirects
    for a in e.authors:
        while is_redirect(a):
            if a in e.authors:
                e.authors.remove(a)
            a = web.ctx.site.get(a.location)
            if not is_redirect(a):
                e.authors.append(a)

    if e.get('works'):
        w = e.works[0].dict()
        work_created = False
    else:
        # Found an edition without a work
        work_created = need_work_save = need_edition_save = True
        w = new_work(e.dict(), rec)
        e.works = [{'key': w['key']}]

    # Update edition fields from the record.
    e, need_matched_edition_save = update_matched_edition(
        e, rec, account_key, from_marc_record
    )

    w = cast("Work", w)  # w is a work now rather than None.
    w, need_matched_work_save = update_matched_work(w, e, rec)

    edits = []
    reply: dict = {
        'success': True,
        'edition': {'key': match, 'status': 'matched'},
        'work': {'key': w['key'], 'status': 'matched'},
    }
    if need_edition_save or need_matched_edition_save:
        reply['edition']['status'] = 'modified'
        edits.append(e.dict())
    if need_work_save or need_matched_work_save:
        reply['work']['status'] = 'created' if work_created else 'modified'
        edits.append(w)
    if edits:
        web.ctx.site.save_many(
            edits, comment='import existing book', action='edit-book'
        )
    if 'ocaid' in rec:
        update_ia_metadata_for_ol_edition(match.split('/')[-1])
    return reply
