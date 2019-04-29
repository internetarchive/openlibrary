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

The title and source_record fields are mandatory.

A record is loaded by calling the load function.

    record = {...}
    response = load(record)

"""
from __future__ import print_function

import re
import json
from time import sleep
from collections import defaultdict
import urllib
import unicodedata
from copy import copy

import web
from infogami import config

import six

from openlibrary.catalog.merge.merge_marc import build_marc
from openlibrary.catalog.utils import mk_norm
from openlibrary.core import lending
from openlibrary import accounts

from load_book import build_query, import_author, east_in_by_statement, InvalidLanguage
from merge import try_merge


import six


re_normalize = re.compile('[^[:alphanum:] ]', re.U)
re_lang = re.compile('^/languages/([a-z]{3})$')

def strip_accents(s):
    """http://stackoverflow.com/questions/517923/what-is-the-best-way-to-remove-accents-in-a-python-unicode-string
    """
    if isinstance(s, str):
        return s
    assert isinstance(s, six.text_type)
    return ''.join((c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))

def normalize(s): # strip non-alphanums and truncate at 25 chars
    norm = strip_accents(s).lower()
    norm = norm.replace(' and ', ' ')
    if norm.startswith('the '):
        norm = norm[4:]
    elif norm.startswith('a '):
        norm = norm[2:]
    return norm.replace(' ', '')[:25]

type_map = {
    'description': 'text',
    'notes': 'text',
    'number_of_pages': 'int',
}

class CoverNotSaved(Exception):
    def __init__(self, f):
        self.f = f
    def __str__(self):
        return "coverstore responded with: '%s'" % self.f

class RequiredField(Exception):
    def __init__(self, f):
        self.f = f
    def __str__(self):
        return "missing required field: '%s'" % self.f

# don't use any of these as work titles
bad_titles = set(('Publications', 'Works. English', 'Missal', 'Works', 'Report', \
    'Letters', 'Calendar', 'Bulletin', 'Plays', 'Sermons', 'Correspondence', \
    'Bill', 'Bills', 'Selections', 'Selected works', 'Selected works. English', \
    'The Novels', 'Laws, etc'))

subject_fields = ['subjects', 'subject_places', 'subject_times', 'subject_people' ]

def get_title(e):
    if not e.get('work_titles'):
        return e['title']
    wt = e['work_titles'][0]
    return e['title'] if wt in bad_titles else e['title']

def find_matching_work(e):
    norm_title = mk_norm(get_title(e))

    seen = set()
    for a in e['authors']:
        q = {
            'type':'/type/work',
            'authors.author': a['key'],
        }
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

def build_author_reply(author_in, edits):
    # modifies edits
    authors = []
    author_reply = []
    for a in author_in:
        new_author = 'key' not in a
        if new_author:
            a['key'] = web.ctx.site.new_key('/type/author')
            edits.append(a)
        authors.append({'key': a['key']})
        author_reply.append({
            'key': a['key'],
            'name': a['name'],
            'status': ('created' if new_author else 'modified'),
        })
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
        w['authors'] = [{'type':{'key': '/type/author_role'}, 'author': akey} for akey in edition['authors']]

    if 'description' in rec:
        w['description'] = {'type': '/type/text', 'value': rec['description']}

    wkey = web.ctx.site.new_key('/type/work')
    if edition.get('covers'):
        w['covers'] = edition['covers']
    w['key'] = wkey
    return w

def load_data(rec, account=None):
    """
    Adds a new Edition to Open Library. Creates a new Work if required,
    otherwise associates the new Edition with an existing Work.

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
            "edition": {"key": <key>, "status": "created"}
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
        cover_id = add_cover(cover_url, ekey, account=account)
        edition['covers'] = [cover_id]

    edits = []
    reply = {}
    author_in = [import_author(a, eastern=east_in_by_statement(rec, a)) for a in edition.get('authors', [])]
    # build_author_reply() adds authors to edits
    (authors, author_reply) = build_author_reply(author_in, edits)

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
                if s not in w.get(k, []):
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

    web.ctx.site.save_many(edits, 'import new book')

    # Writes back `openlibrary_edition` and `openlibrary_work` to
    # archive.org item after successful import:
    update_ia_metadata_for_ol_edition(ekey.split('/')[-1])

    reply['success'] = True
    reply['edition'] = {'key': ekey, 'status': 'created'}
    reply['work'] = {'key': wkey, 'status': work_state}
    return reply

def is_redirect(thing):
    if not thing:
        return False
    return thing.type.key == '/type/redirect'

def find_match(e1, edition_pool):
    seen = set()
    for k, v in edition_pool.iteritems():
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
                    print('following redirect %s => %s' % (edition_key, thing['location']))
                    edition_key = thing['location']
            if not found:
                continue
            if try_merge(e1, edition_key, thing):
                return edition_key

def isbns_from_record(rec):
    """
    Returns a list of all isbns from the various possible isbn fields.

    :param dict rec: Edition import record
    :rtype: list
    """
    isbns = rec.get('isbn', []) + rec.get('isbn_10', []) + rec.get('isbn_13', [])
    isbns = [isbn.replace('-', '').strip() for isbn in isbns]
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
    pool['title'].update(set(editions_matched(rec, 'normalized_title_', normalize(rec['title']))))

    # Find records with matching ISBNs
    isbns = isbns_from_record(rec)
    if isbns:
        pool['isbn'] = set(editions_matched(rec, 'isbn_', isbns))

    return dict((k, list(v)) for k, v in pool.iteritems() if v)

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

def editions_matched(rec, key, value=None):
    """
    Search OL for editions matching record's 'key' value.

    :param dict rec: Edition import record
    :param str key: Key to search on
    :param list|str value: Value or Values to use, overriding record values
    :rtpye: list
    :return: List of edition keys ["/books/OL..M",]
    """
    if value is None and key not in rec:
        return []

    if value is None:
        value = rec[key]
    q = {
        'type':'/type/edition',
        key: value
    }
    ekeys = list(web.ctx.site.things(q))
    return ekeys

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

    isbns = isbns_from_record(rec)
    if isbns:
        ekeys = editions_matched(rec, 'isbn_', isbns)
        if ekeys:
            return ekeys[0]

    # only searches for the first value from these lists
    for f in 'source_records', 'oclc_numbers', 'lccn':
        if rec.get(f):
            ekeys = editions_matched(rec, f, rec[f][0])
            if ekeys:
                return ekeys[0]
    return False

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
    for field, editions in edition_pool.iteritems():
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
                     existing_value = [str(re_lang.match(l.key).group(1)) for l in existing_value]
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

def add_cover(cover_url, ekey, account=None):
    """
    Adds a cover to coverstore and returns the cover id.

    :param str cover_url: URL of cover image
    :param str ekey: Edition key /book/OL..M
    :rtype: int
    :return: Cover id
    """
    olid = ekey.split("/")[-1]
    coverstore_url = config.get('coverstore_url').rstrip('/')
    upload_url = coverstore_url + '/b/upload2'
    if upload_url.startswith("//"):
        upload_url = "{0}:{1}".format(web.ctx.get("protocol", "http"), upload_url)
    user = account or accounts.get_current_user()
    params = {
        'author': user.get('key') or user.get('_key'),
        'data': None,
        'source_url': cover_url,
        'olid': olid,
        'ip': web.ctx.ip,
    }
    reply = None
    for attempt in range(10):
        try:
            res = urllib.urlopen(upload_url, urllib.urlencode(params))
        except IOError:
            print('retry, attempt', attempt)
            sleep(2)
            continue
        body = res.read()
        if res.getcode() == 500:
            raise CoverNotSaved(body)
        if body not in ['', 'None']:
            reply = json.loads(body)
            if res.getcode() == 200 and 'id' in reply:
                break
        print('retry, attempt', attempt)
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
    access_key = lending.config_ia_ol_metadata_write_s3 and lending.config_ia_ol_metadata_write_s3['s3_key']
    secret_key = lending.config_ia_ol_metadata_write_s3 and lending.config_ia_ol_metadata_write_s3['s3_secret']
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
        return ('%s failed: %s' % (item.identifier, r.content))
    else:
        return ("success for %s" % item.identifier)

def update_ia_metadata_for_ol_edition(edition_id):
    """An ol_edition is of the form OL...M"""

    data = {'error': 'No qualifying edition'}
    if edition_id:
        ed = web.ctx.site.get('/books/%s' % edition_id)
        if ed.ocaid:
            work = ed.works[0] if ed.get('works') else None
            if work and work.key:
                item = get_ia_item(ed.ocaid)
                work_id = work.key.split('/')[2]
                r = modify_ia_item(item, {
                    'openlibrary_work': work_id,
                    'openlibrary_edition': edition_id
                })
                if r.status_code != 200:
                    data = {'error': '%s failed: %s' % (item.identifier, r.content)}
                else:
                    data = item.metadata
    return data

def load(rec, account=None):
    """Given a record, tries to add/match that edition in the system.

    Record is a dictionary containing all the metadata of the edition.
    The following fields are mandatory:

        * title
        * source_records
    """
    if not rec.get('title'):
        raise RequiredField('title')
    if not rec.get('source_records'):
        raise RequiredField('source_records')
    if isinstance(rec['source_records'], six.string_types):
        rec['source_records'] = [rec['source_records']]

    edition_pool = build_pool(rec)
    if not edition_pool:
        # No match candidates found, add edition
        return load_data(rec, account=account)

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
        return load_data(rec, account=account)

    # We have an edition match at this point
    need_work_save = need_edition_save = False
    w = None
    e = web.ctx.site.get(match)
    if e.get('works'):
        w = e.works[0].dict()
        work_created = False
    else:
        # Found an edition without a work
        work_created = need_work_save = need_edition_save = True
        w = new_work(e.dict(), rec)
        e.works = [{'key': w['key']}]

    # Add subjects to work, if not already present
    if 'subjects' in rec:
        work_subjects = list(w.get('subjects', []))
        for s in rec['subjects']:
            if s not in work_subjects:
                work_subjects.append(s)
                need_work_save = True
        if need_work_save and work_subjects:
            w['subjects'] = work_subjects

    # Add cover to edition
    if 'cover' in rec and not e.covers:
        cover_url = rec['cover']
        cover_id = add_cover(cover_url, e.key, account=account)
        if cover_id:
            e['covers'] = [cover_id]
            need_edition_save = True

    # Add cover to work, if needed
    if not w.get('covers') and e.get('covers'):
        w['covers'] = [e['covers'][0]]
        need_work_save = True

    # Add description to work, if needed
    if not w.get('description') and e.get('description'):
        w['description'] = e['description']
        need_work_save = True

    # Add authors to work, if needed
    if not w.get('authors'):
        authors = [import_author(a) for a in rec.get('authors', [])]
        w['authors'] = [{'type':{'key': '/type/author_role'}, 'author': a.key} for a in authors if a.get('key')]
        if w.get('authors'):
            need_work_save = True

    # Add ocaid to edition (str), if needed
    if 'ocaid' in rec and not e.ocaid:
        e['ocaid'] = rec['ocaid']
        need_edition_save = True

    edition_fields = [
        'local_id', 'ia_box_id', 'ia_loaded_id', 'source_records']
    # XXX Todos:
    # only consider `source_records` for newly created work
    # or if field originally missing:
    #if work_created and not e.get('source_records'):
    #    edition_fields.append('source_records')
    for f in edition_fields:
        if f not in rec:
            continue
        # ensure values is a list
        values = rec[f] if isinstance(rec[f], list) else [rec[f]]
        if f in e:
            # get values from rec that are not currently on the edition
            to_add = [v for v in values if v not in e[f]]
            e[f] += to_add
        else:
            e[f] = to_add = values
        if to_add:
            need_edition_save = True

    edits = []
    reply = {
        'success': True,
        'edition': {'key': match, 'status': 'matched'},
        'work': {'key': w['key'], 'status': 'matched'},
    }
    if need_edition_save:
        reply['edition']['status'] = 'modified'
        edits.append(e.dict())
    if need_work_save:
        reply['work']['status'] = 'created' if work_created else 'modified'
        edits.append(w)
    if edits:
        web.ctx.site.save_many(edits, 'import existing book')
    if 'ocaid' in rec:
        update_ia_metadata_for_ol_edition(match.split('/')[-1])
    return reply
