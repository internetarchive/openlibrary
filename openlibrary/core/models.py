"""Models of various OL objects.
"""
import web
import requests
from collections import defaultdict

from infogami.infobase import client

from openlibrary.core import helpers as h

# TODO: fix this. openlibrary.core should not import plugins.
from openlibrary import accounts
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.core.helpers import private_collection_in
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.booknotes import Booknotes
from openlibrary.core.observations import Observations
from openlibrary.core.ratings import Ratings
from openlibrary.utils.isbn import to_isbn_13, isbn_13_to_isbn_10, canonical
from openlibrary.core.vendors import create_edition_from_amazon_metadata

# Seed might look unused, but removing it causes an error :/
from openlibrary.core.lists.model import ListMixin, Seed  # noqa: F401
from . import cache, waitinglist

import urllib

from .ia import get_metadata_direct
from .waitinglist import WaitingLoan
from ..accounts import OpenLibraryAccount
from ..plugins.upstream.utils import get_coverstore_url, get_coverstore_public_url


def _get_ol_base_url():
    # Anand Oct 2013
    # Looks like the default value when called from script
    if "[unknown]" in web.ctx.home:
        return "https://openlibrary.org"
    else:
        return web.ctx.home


class Image:
    def __init__(self, site, category, id):
        self._site = site
        self.category = category
        self.id = id

    def info(self):
        url = f'{get_coverstore_url()}/{self.category}/id/{self.id}.json'
        if url.startswith("//"):
            url = "http:" + url
        try:
            d = requests.get(url).json()
            d['created'] = h.parse_datetime(d['created'])
            if d['author'] == 'None':
                d['author'] = None
            d['author'] = d['author'] and self._site.get(d['author'])

            return web.storage(d)
        except OSError:
            # coverstore is down
            return None

    def url(self, size="M"):
        """Get the public URL of the image."""
        coverstore_url = get_coverstore_public_url()
        return f"{coverstore_url}/{self.category}/id/{self.id}-{size.upper()}.jpg"

    def __repr__(self):
        return "<image: %s/%d>" % (self.category, self.id)


class Thing(client.Thing):
    """Base class for all OL models."""

    @cache.method_memoize
    def get_history_preview(self):
        """Returns history preview."""
        history = self._get_history_preview()
        history = web.storage(history)

        history.revision = self.revision
        history.lastest_revision = self.revision
        history.created = self.created

        def process(v):
            """Converts entries in version dict into objects."""
            v = web.storage(v)
            v.created = h.parse_datetime(v.created)
            v.author = v.author and self._site.get(v.author, lazy=True)
            return v

        history.initial = [process(v) for v in history.initial]
        history.recent = [process(v) for v in history.recent]

        return history

    @cache.memoize(engine="memcache", key=lambda self: ("d" + self.key, "h"))
    def _get_history_preview(self):
        h = {}
        if self.revision < 5:
            h['recent'] = self._get_versions(limit=5)
            h['initial'] = h['recent'][-1:]
            h['recent'] = h['recent'][:-1]
        else:
            h['initial'] = self._get_versions(limit=1, offset=self.revision - 1)
            h['recent'] = self._get_versions(limit=4)
        return h

    def _get_versions(self, limit, offset=0):
        q = {"key": self.key, "limit": limit, "offset": offset}
        versions = self._site.versions(q)
        for v in versions:
            v.created = v.created.isoformat()
            v.author = v.author and v.author.key

            # XXX-Anand: hack to avoid too big data to be stored in memcache.
            # v.changes is not used and it contrinutes to memcache bloat in a big way.
            v.changes = '[]'
        return versions

    def get_most_recent_change(self):
        """Returns the most recent change."""
        preview = self.get_history_preview()
        if preview.recent:
            return preview.recent[0]
        else:
            return preview.initial[0]

    def prefetch(self):
        """Prefetch all the anticipated data."""
        preview = self.get_history_preview()
        authors = {v.author.key for v in preview.initial + preview.recent if v.author}
        # preload them
        self._site.get_many(list(authors))

    def _make_url(self, label, suffix, relative=True, **params):
        """Make url of the form $key/$label$suffix?$params."""
        if label is not None:
            u = self.key + "/" + h.urlsafe(label) + suffix
        else:
            u = self.key + suffix
        if params:
            u += '?' + urllib.parse.urlencode(params)
        if not relative:
            u = _get_ol_base_url() + u
        return u

    def get_url(self, suffix="", **params):
        """Constructs a URL for this page with given suffix and query params.

        The suffix is added to the URL of the page and query params are appended after adding "?".
        """
        return self._make_url(label=self.get_url_suffix(), suffix=suffix, **params)

    def get_url_suffix(self):
        """Returns the additional suffix that is added to the key to get the URL of the page.

        Models of Edition, Work etc. should extend this to return the suffix.

        This is used to construct the URL of the page. By default URL is the
        key of the page. If this method returns None, nothing is added to the
        key. If this method returns a string, it is sanitized and added to key
        after adding a "/".
        """
        return None

    def _get_lists(self, limit=50, offset=0, sort=True):
        # cache the default case
        if limit == 50 and offset == 0:
            keys = self._get_lists_cached()
        else:
            keys = self._get_lists_uncached(limit=limit, offset=offset)

        lists = self._site.get_many(keys)
        if sort:
            lists = h.safesort(lists, reverse=True, key=lambda list: list.last_modified)
        return lists

    @cache.memoize(engine="memcache", key=lambda self: ("d" + self.key, "l"))
    def _get_lists_cached(self):
        return self._get_lists_uncached(limit=50, offset=0)

    def _get_lists_uncached(self, limit, offset):
        q = {
            "type": "/type/list",
            "seeds": {"key": self.key},
            "limit": limit,
            "offset": offset,
        }
        return self._site.things(q)

    def _get_d(self):
        """Returns the data that goes into memcache as d/$self.key.
        Used to measure the memcache usage.
        """
        return {
            "h": self._get_history_preview(),
            "l": self._get_lists_cached(),
        }


class Edition(Thing):
    """Class to represent /type/edition objects in OL."""

    def url(self, suffix="", **params):
        return self.get_url(suffix, **params)

    def get_url_suffix(self):
        return self.title or "untitled"

    def __repr__(self):
        return "<Edition: %s>" % repr(self.title)

    __str__ = __repr__

    def full_title(self):
        # retained for backward-compatibility. Is anybody using this really?
        return self.title

    def get_publish_year(self):
        if self.publish_date:
            m = web.re_compile(r"(\d\d\d\d)").search(self.publish_date)
            return m and int(m.group(1))

    def get_lists(self, limit=50, offset=0, sort=True):
        return self._get_lists(limit=limit, offset=offset, sort=sort)

    def get_ebook_info(self):
        """Returns the ebook info with the following fields.

        * read_url - url to read the book
        * borrow_url - url to borrow the book
        * borrowed - True if the book is already borrowed
        * daisy_url - url to access the daisy format of the book
        * daisy_only - a boolean indicating whether book avail
                       exclusively as daisy

        Sample return values:

            {
                "read_url": "http://www.archive.org/stream/foo00bar",
                "daisy_url": "/books/OL1M/foo/daisy"
            }

            {
                "daisy_url": "/books/OL1M/foo/daisy",
                "borrow_url": "/books/OL1M/foo/borrow",
                "borrowed": False
            }

        """
        d = {}
        if self.ocaid:
            d['has_ebook'] = True
            d['daisy_url'] = self.url('/daisy')
            d['daisy_only'] = True

            collections = self.get_ia_collections()
            borrowable = self.in_borrowable_collection()

            if borrowable:
                d['borrow_url'] = self.url("/borrow")
                key = "ebooks" + self.key
                doc = self._site.store.get(key) or {}
                # caution, solr borrow status may be stale!
                d['borrowed'] = doc.get("borrowed") == "true"
                d['daisy_only'] = False
            elif 'printdisabled' not in collections:
                d['read_url'] = "https://archive.org/stream/%s" % self.ocaid
                d['daisy_only'] = False
        return d

    def get_ia_collections(self):
        return self.get_ia_meta_fields().get("collection", [])

    def is_access_restricted(self):
        collections = self.get_ia_collections()
        return (
            'printdisabled' in collections
            or 'lendinglibrary' in collections
            or self.get_ia_meta_fields().get("access-restricted") is True
        )

    def is_in_private_collection(self):
        """Private collections are lendable books that should not be
        linked/revealed from OL
        """
        return private_collection_in(self.get_ia_collections())

    def in_borrowable_collection(self):
        collections = self.get_ia_collections()
        return (
            'lendinglibrary' in collections or 'inlibrary' in collections
        ) and not self.is_in_private_collection()

    def get_waitinglist(self):
        """Returns list of records for all users currently waiting for this book."""
        return waitinglist.get_waitinglist_for_book(self.key)

    @property  # type: ignore[misc]
    @cache.method_memoize
    def ia_metadata(self):
        ocaid = self.get('ocaid')
        return get_metadata_direct(ocaid, cache=False) if ocaid else {}

    @property  # type: ignore[misc]
    @cache.method_memoize
    def sponsorship_data(self):
        was_sponsored = 'openlibraryscanningteam' in self.ia_metadata.get(
            'collection', []
        )
        if not was_sponsored:
            return None

        donor = self.ia_metadata.get('donor')

        return web.storage(
            {
                'donor': donor,
                'donor_account': OpenLibraryAccount.get_by_link(donor)
                if donor
                else None,
                'donor_msg': self.ia_metadata.get('donor_msg'),
            }
        )

    def get_waitinglist_size(self, ia=False):
        """Returns the number of people on waiting list to borrow this book."""
        return waitinglist.get_waitinglist_size(self.key)

    def get_loans(self):
        from ..plugins.upstream import borrow

        return borrow.get_edition_loans(self)

    def get_ia_download_link(self, suffix):
        """Returns IA download link for given suffix.
        The suffix is usually one of '.pdf', '.epub', '.mobi', '_djvu.txt'
        """
        if self.ocaid:
            metadata = self.get_ia_meta_fields()
            # The _filenames field is set by ia.get_metadata function
            filenames = metadata.get("_filenames")
            if filenames:
                filename = next((f for f in filenames if f.endswith(suffix)), None)
            else:
                # filenames is not in cache.
                # This is required only until all the memcache entries expire
                filename = self.ocaid + suffix

            if filename is None and self.is_ia_scan():
                # IA scans will have all the required suffixes.
                # Sometimes they are generated on the fly.
                filename = self.ocaid + suffix

            if filename:
                return f"https://archive.org/download/{self.ocaid}/{filename}"

    @classmethod
    def from_isbn(cls, isbn):
        """Attempts to fetch an edition by isbn, or if no edition is found,
        attempts to import from amazon
        :param str isbn:
        :rtype: edition|None
        :return: an open library work for this isbn
        """
        isbn = canonical(isbn)

        if len(isbn) not in [10, 13]:
            return None  # consider raising ValueError

        isbn13 = to_isbn_13(isbn)
        if isbn13 is None:
            return None  # consider raising ValueError
        isbn10 = isbn_13_to_isbn_10(isbn13)

        # Attempt to fetch book from OL
        for isbn in [isbn13, isbn10]:
            if isbn:
                matches = web.ctx.site.things(
                    {"type": "/type/edition", 'isbn_%s' % len(isbn): isbn}
                )
                if matches:
                    return web.ctx.site.get(matches[0])

        # Attempt to create from amazon, then fetch from OL
        key = (isbn10 or isbn13) and create_edition_from_amazon_metadata(
            isbn10 or isbn13
        )
        if key:
            return web.ctx.site.get(key)

    def is_ia_scan(self):
        metadata = self.get_ia_meta_fields()
        # all IA scans will have scanningcenter field set
        return bool(metadata.get("scanningcenter"))

    def make_work_from_orphaned_edition(self):
        """
        Create a dummy work from an orphaned_edition.
        """
        return web.ctx.site.new(
            '',
            {
                'key': '',
                'type': {'key': '/type/work'},
                'title': self.title,
                'authors': [
                    {'type': {'key': '/type/author_role'}, 'author': {'key': a['key']}}
                    for a in self.get('authors', [])
                ],
                'editions': [self],
                'subjects': self.get('subjects', []),
            },
        )


class Work(Thing):
    """Class to represent /type/work objects in OL."""

    def url(self, suffix="", **params):
        return self.get_url(suffix, **params)

    def get_url_suffix(self):
        return self.title or "untitled"

    def __repr__(self):
        return "<Work: %s>" % repr(self.key)

    __str__ = __repr__

    @property  # type: ignore[misc]
    @cache.method_memoize
    @cache.memoize(engine="memcache", key=lambda self: ("d" + self.key, "e"))
    def edition_count(self):
        return self._site._request("/count_editions_by_work", data={"key": self.key})

    def get_lists(self, limit=50, offset=0, sort=True):
        return self._get_lists(limit=limit, offset=offset, sort=sort)

    def get_users_rating(self, username):
        if not username:
            return None
        work_id = extract_numeric_id_from_olid(self.key)
        rating = Ratings.get_users_rating_for_work(username, work_id)
        return rating

    def get_users_read_status(self, username):
        if not username:
            return None
        work_id = extract_numeric_id_from_olid(self.key)
        status_id = Bookshelves.get_users_read_status_of_work(username, work_id)
        return status_id

    def get_users_notes(self, username, edition_olid=None):
        if not username:
            return None
        work_id = extract_numeric_id_from_olid(self.key)
        edition_id = extract_numeric_id_from_olid(edition_olid) if edition_olid else -1
        return Booknotes.get_patron_booknote(username, work_id, edition_id=edition_id)

    def has_book_note(self, username, edition_olid):
        if not username:
            return False
        work_id = extract_numeric_id_from_olid(self.key)
        edition_id = extract_numeric_id_from_olid(edition_olid)
        return (
            len(Booknotes.get_patron_booknote(username, work_id, edition_id=edition_id))
            > 0
        )

    def get_users_observations(self, username):
        if not username:
            return None
        work_id = extract_numeric_id_from_olid(self.key)
        raw_observations = Observations.get_patron_observations(username, work_id)
        formatted_observations = defaultdict(list)

        for r in raw_observations:
            kv_pair = Observations.get_key_value_pair(r['type'], r['value'])
            formatted_observations[kv_pair.key].append(kv_pair.value)

        return formatted_observations

    def get_num_users_by_bookshelf(self):
        if not self.key:  # a dummy work
            return {'want-to-read': 0, 'currently-reading': 0, 'already-read': 0}
        work_id = extract_numeric_id_from_olid(self.key)
        num_users_by_bookshelf = Bookshelves.get_num_users_by_bookshelf_by_work_id(
            work_id
        )
        return {
            'want-to-read': num_users_by_bookshelf.get(
                Bookshelves.PRESET_BOOKSHELVES['Want to Read'], 0
            ),
            'currently-reading': num_users_by_bookshelf.get(
                Bookshelves.PRESET_BOOKSHELVES['Currently Reading'], 0
            ),
            'already-read': num_users_by_bookshelf.get(
                Bookshelves.PRESET_BOOKSHELVES['Already Read'], 0
            ),
        }

    def get_rating_stats(self):
        if not self.key:  # a dummy work
            return {'avg_rating': 0, 'num_ratings': 0}
        work_id = extract_numeric_id_from_olid(self.key)
        rating_stats = Ratings.get_rating_stats(work_id)
        if rating_stats and rating_stats['num_ratings'] > 0:
            return {
                'avg_rating': round(rating_stats['avg_rating'], 2),
                'num_ratings': rating_stats['num_ratings'],
            }

    def _get_d(self):
        """Returns the data that goes into memcache as d/$self.key.
        Used to measure the memcache usage.
        """
        return {
            "h": self._get_history_preview(),
            "l": self._get_lists_cached(),
            "e": self.edition_count,
        }

    def _make_subject_link(self, title, prefix=""):
        slug = web.safestr(title.lower().replace(' ', '_').replace(',', ''))
        key = f"/subjects/{prefix}{slug}"
        return web.storage(key=key, title=title, slug=slug)

    def get_subject_links(self, type="subject"):
        """Returns all the subjects as link objects.
        Each link is a web.storage object with title and key fields.

        The type should be one of subject, place, person or time.
        """
        if type == 'subject':
            return [self._make_subject_link(s) for s in self.get_subjects()]
        elif type == 'place':
            return [self._make_subject_link(s, "place:") for s in self.subject_places]
        elif type == 'person':
            return [self._make_subject_link(s, "person:") for s in self.subject_people]
        elif type == 'time':
            return [self._make_subject_link(s, "time:") for s in self.subject_times]
        else:
            return []

    def get_ebook_info(self):
        """Returns the ebook info with the following fields.

        * read_url - url to read the book
        * borrow_url - url to borrow the book
        * borrowed - True if the book is already borrowed
        * daisy_url - url to access the daisy format of the book

        Sample return values:

            {
                "read_url": "http://www.archive.org/stream/foo00bar",
                "daisy_url": "/books/OL1M/foo/daisy"
            }

            {
                "daisy_url": "/books/OL1M/foo/daisy",
                "borrow_url": "/books/OL1M/foo/borrow",
                "borrowed": False
            }
        """
        solrdata = web.storage(self._solr_data or {})
        d = {}
        if solrdata.get('has_fulltext') and solrdata.get('public_scan_b'):
            d['read_url'] = f"https://archive.org/stream/{solrdata.ia[0]}"
            d['has_ebook'] = True
        elif solrdata.get('lending_edition_s'):
            d['borrow_url'] = f"/books/{solrdata.lending_edition_s}/x/borrow"
            d['has_ebook'] = True
        if solrdata.get('ia'):
            d['ia'] = solrdata.get('ia')
        return d

    @staticmethod
    def get_redirect_chain(work_key: str) -> list:
        resolved_key = None
        redirect_chain = []
        key = work_key
        while not resolved_key:
            thing = web.ctx.site.get(key)
            redirect_chain.append(thing)
            if thing.type.key == "/type/redirect":
                key = thing.location
            else:
                resolved_key = thing.key
        return redirect_chain


class Author(Thing):
    """Class to represent /type/author objects in OL."""

    def url(self, suffix="", **params):
        return self.get_url(suffix, **params)

    def get_url_suffix(self):
        return self.name or "unnamed"

    def __repr__(self):
        return "<Author: %s>" % repr(self.key)

    __str__ = __repr__

    def foaf_agent(self):
        """
        Friend of a friend ontology Agent type. http://xmlns.com/foaf/spec/#term_Agent
        https://en.wikipedia.org/wiki/FOAF_(ontology)
        """
        if self.get('entity_type') == 'org':
            return 'Organization'
        elif self.get('birth_date') or self.get('death_date'):
            return 'Person'
        return 'Agent'

    def get_edition_count(self):
        return self._site._request('/count_editions_by_author', data={'key': self.key})

    edition_count = property(get_edition_count)

    def get_lists(self, limit=50, offset=0, sort=True):
        return self._get_lists(limit=limit, offset=offset, sort=sort)


class User(Thing):

    DEFAULT_PREFERENCES = {
        'updates': 'no',
        'public_readlog': 'no'
        # New users are now public by default for new patrons
        # As of 2020-05, OpenLibraryAccount.create will
        # explicitly set public_readlog: 'yes'.
        # Legacy acconts w/ no public_readlog key
        # will continue to default to 'no'
    }

    def get_status(self):
        account = self.get_account() or {}
        return account.get("status")

    def get_usergroups(self):
        keys = self._site.things({'type': '/type/usergroup', 'members': self.key})
        return self._site.get_many(keys)

    usergroups = property(get_usergroups)

    def get_account(self):
        username = self.get_username()
        return accounts.find(username=username)

    def get_email(self):
        account = self.get_account() or {}
        return account.get("email")

    def get_username(self):
        return self.key.split("/")[-1]

    def preferences(self):
        key = "%s/preferences" % self.key
        prefs = web.ctx.site.get(key)
        return (prefs and prefs.dict().get('notifications')) or self.DEFAULT_PREFERENCES

    def save_preferences(self, new_prefs, msg='updating user preferences'):
        key = '%s/preferences' % self.key
        old_prefs = web.ctx.site.get(key)
        prefs = (old_prefs and old_prefs.dict()) or {
            'key': key,
            'type': {'key': '/type/object'},
        }
        if 'notifications' not in prefs:
            prefs['notifications'] = self.DEFAULT_PREFERENCES
        prefs['notifications'].update(new_prefs)
        web.ctx.site.save(prefs, msg)

    def is_usergroup_member(self, usergroup):
        if not usergroup.startswith('/usergroup/'):
            usergroup = '/usergroup/%s' % usergroup
        return usergroup in [g.key for g in self.usergroups]

    def is_printdisabled(self):
        return web.cookies().get('pd')

    def is_admin(self):
        return self.is_usergroup_member('/usergroup/admin')

    def is_librarian(self):
        return self.is_usergroup_member('/usergroup/librarians')

    def in_sponsorship_beta(self):
        return self.is_usergroup_member('/usergroup/sponsors')

    def is_beta_tester(self):
        return self.is_usergroup_member('/usergroup/beta-testers')

    def has_librarian_tools(self):
        return self.is_usergroup_member('/usergroup/librarian-tools')

    def is_read_only(self):
        return self.is_usergroup_member('/usergroup/read-only')

    def get_lists(self, seed=None, limit=100, offset=0, sort=True):
        """Returns all the lists of this user.

        When seed is specified, this returns all the lists which contain the
        given seed.

        seed could be an object or a string like "subject:cheese".
        """
        # cache the default case
        if seed is None and limit == 100 and offset == 0:
            keys = self._get_lists_cached()
        else:
            keys = self._get_lists_uncached(seed=seed, limit=limit, offset=offset)

        lists = self._site.get_many(keys)
        if sort:
            lists = h.safesort(lists, reverse=True, key=lambda list: list.last_modified)
        return lists

    @cache.memoize(engine="memcache", key=lambda self: ("d" + self.key, "l"))
    def _get_lists_cached(self):
        return self._get_lists_uncached(limit=100, offset=0)

    def _get_lists_uncached(self, seed=None, limit=100, offset=0):
        q = {
            "type": "/type/list",
            "key~": self.key + "/lists/*",
            "limit": limit,
            "offset": offset,
        }
        if seed:
            if isinstance(seed, Thing):
                seed = {"key": seed.key}
            q['seeds'] = seed

        return self._site.things(q)

    def new_list(self, name, description, seeds, tags=None):
        tags = tags or []
        """Creates a new list object with given name, description, and seeds.

        seeds must be a list containing references to author, edition, work or subject strings.

        Sample seeds:

            {"key": "/authors/OL1A"}
            {"key": "/books/OL1M"}
            {"key": "/works/OL1W"}
            "subject:love"
            "place:san_francisco"
            "time:1947"
            "person:gerge"

        The caller must call list._save(...) to save the list.
        """
        id = self._site.seq.next_value("list")

        # since the owner is part of the URL, it might be difficult to handle
        # change of ownerships. Need to think of a way to handle redirects.
        key = f"{self.key}/lists/OL{id}L"
        doc = {
            "key": key,
            "type": {"key": "/type/list"},
            "name": name,
            "description": description,
            "seeds": seeds,
            "tags": tags,
        }
        return self._site.new(key, doc)

    def is_waiting_for(self, book):
        """Returns True if this user is waiting to loan given book."""
        return waitinglist.is_user_waiting_for(self.key, book.key)

    def get_waitinglist(self):
        """Returns list of records for all the books the user is currently waiting for."""
        return waitinglist.get_waitinglist_for_user(self.key)

    def has_borrowed(self, book):
        """Returns True if this user has borrowed given book."""
        loan = self.get_loan_for(book.ocaid)
        return loan is not None

    def get_loan_for(self, ocaid):
        """Returns the loan object for given ocaid.

        Returns None if this user hasn't borrowed the given book.
        """
        from ..plugins.upstream import borrow

        loans = borrow.get_loans(self)
        for loan in loans:
            if ocaid == loan['ocaid']:
                return loan

    def get_waiting_loan_for(self, ocaid):
        """
        :param str or None ocaid:
        :rtype: dict (e.g. {position: number})
        """
        return ocaid and WaitingLoan.find(self.key, ocaid)

    def __repr__(self):
        return "<User: %s>" % repr(self.key)

    __str__ = __repr__

    def render_link(self, cls=None):
        """
        Generate an HTML link of this user
        :param str cls: HTML class to add to the link
        :rtype: str
        """
        extra_attrs = ''
        if cls:
            extra_attrs += 'class="%s" ' % cls
        # Why nofollow?
        return f'<a rel="nofollow" href="{self.key}" {extra_attrs}>{web.net.htmlquote(self.displayname)}</a>'

    def set_data(self, data):
        self._data = data
        self._save()


class List(Thing, ListMixin):
    """Class to represent /type/list objects in OL.

    List contains the following properties:

        * name - name of the list
        * description - detailed description of the list (markdown)
        * members - members of the list. Either references or subject strings.
        * cover - id of the book cover. Picked from one of its editions.
        * tags - list of tags to describe this list.
    """

    def url(self, suffix="", **params):
        return self.get_url(suffix, **params)

    def get_url_suffix(self):
        return self.name or "unnamed"

    def get_owner(self):
        match = web.re_compile(r"(/people/[^/]+)/lists/OL\d+L").match(self.key)
        if match:
            key = match.group(1)
            return self._site.get(key)

    def get_cover(self):
        """Returns a cover object."""
        return self.cover and Image(self._site, "b", self.cover)

    def get_tags(self):
        """Returns tags as objects.

        Each tag object will contain name and url fields.
        """
        return [web.storage(name=t, url=self.key + "/tags/" + t) for t in self.tags]

    def _get_subjects(self):
        """Returns list of subjects inferred from the seeds.
        Each item in the list will be a storage object with title and url.
        """
        # sample subjects
        return [
            web.storage(title="Cheese", url="/subjects/cheese"),
            web.storage(title="San Francisco", url="/subjects/place:san_francisco"),
        ]

    def add_seed(self, seed):
        """Adds a new seed to this list.

        seed can be:
            - author, edition or work object
            - {"key": "..."} for author, edition or work objects
            - subject strings.
        """
        if isinstance(seed, Thing):
            seed = {"key": seed.key}

        index = self._index_of_seed(seed)
        if index >= 0:
            return False
        else:
            self.seeds = self.seeds or []
            self.seeds.append(seed)
            return True

    def remove_seed(self, seed):
        """Removes a seed for the list."""
        if isinstance(seed, Thing):
            seed = {"key": seed.key}

        index = self._index_of_seed(seed)
        if index >= 0:
            self.seeds.pop(index)
            return True
        else:
            return False

    def _index_of_seed(self, seed):
        for i, s in enumerate(self.seeds):
            if isinstance(s, Thing):
                s = {"key": s.key}
            if s == seed:
                return i
        return -1

    def __repr__(self):
        return f"<List: {self.key} ({self.name!r})>"


class UserGroup(Thing):
    @classmethod
    def from_key(cls, key):
        """
        :param str key: e.g. /usergroup/sponsor-waitlist
        :rtype: UserGroup | None
        """
        if not key.startswith('/usergroup/'):
            key = "/usergroup/%s" % key
        return web.ctx.site.get(key)

    def add_user(self, userkey):
        """Administrative utility (designed to be used in conjunction with
        accounts.RunAs) to add a patron to a usergroup

        :param str userkey: e.g. /people/mekBot
        """
        if not web.ctx.site.get(userkey):
            raise KeyError("Invalid userkey")

        # Make sure userkey not already in group members:
        members = self.get('members', [])
        if not any(userkey == member['key'] for member in members):
            members.append({'key': userkey})
            self.members = members
            web.ctx.site.save(self.dict(), f"Adding {userkey} to {self.key}")

    def remove_user(self, userkey):
        if not web.ctx.site.get(userkey):
            raise KeyError("Invalid userkey")

        members = self.get('members', [])

        # find index of userkey and remove user
        for i, m in enumerate(members):
            if m.get('key', None) == userkey:
                members.pop(i)
                break

        self.members = members
        web.ctx.site.save(self.dict(), f"Removing {userkey} from {self.key}")


class Subject(web.storage):
    def get_lists(self, limit=1000, offset=0, sort=True):
        q = {
            "type": "/type/list",
            "seeds": self.get_seed(),
            "limit": limit,
            "offset": offset,
        }
        keys = web.ctx.site.things(q)
        lists = web.ctx.site.get_many(keys)
        if sort:
            lists = h.safesort(lists, reverse=True, key=lambda list: list.last_modified)
        return lists

    def get_seed(self):
        seed = self.key.split("/")[-1]
        if seed.split(":")[0] not in ["place", "person", "time"]:
            seed = "subject:" + seed
        return seed

    def url(self, suffix="", relative=True, **params):
        u = self.key + suffix
        if params:
            u += '?' + urllib.parse.urlencode(params)
        if not relative:
            u = _get_ol_base_url() + u
        return u

    # get_url is a common method available in all Models.
    # Calling it `get_url` instead of `url` because there are some types that
    # have a property with name `url`.
    get_url = url

    def get_default_cover(self):
        for w in self.works:
            cover_id = w.get("cover_id")
            if cover_id:
                return Image(web.ctx.site, "b", cover_id)


def register_models():
    client.register_thing_class(None, Thing)  # default
    client.register_thing_class('/type/edition', Edition)
    client.register_thing_class('/type/work', Work)
    client.register_thing_class('/type/author', Author)
    client.register_thing_class('/type/user', User)
    client.register_thing_class('/type/list', List)
    client.register_thing_class('/type/usergroup', UserGroup)


def register_types():
    """Register default types for various path patterns used in OL."""
    from infogami.utils import types

    types.register_type('^/authors/[^/]*$', '/type/author')
    types.register_type('^/books/[^/]*$', '/type/edition')
    types.register_type('^/works/[^/]*$', '/type/work')
    types.register_type('^/languages/[^/]*$', '/type/language')

    types.register_type('^/usergroup/[^/]*$', '/type/usergroup')
    types.register_type('^/permission/[^/]*$', '/type/permission')

    types.register_type('^/(css|js)/[^/]*$', '/type/rawtext')
