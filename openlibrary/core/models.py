"""Models of various OL objects."""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, TypedDict
from urllib.parse import urlencode

import requests
import web

from infogami.infobase import client

# TODO: fix this. openlibrary.core should not import plugins.
from openlibrary import accounts
from openlibrary.catalog import add_book  # noqa: F401 side effects may be needed
from openlibrary.core import lending
from openlibrary.core.bestbook import Bestbook
from openlibrary.core.booknotes import Booknotes
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.follows import PubSub
from openlibrary.core.helpers import (
    parse_datetime,
    private_collection_in,
    safesort,
    urlsafe,
)
from openlibrary.core.imports import ImportItem
from openlibrary.core.observations import Observations
from openlibrary.core.ratings import Ratings
from openlibrary.core.vendors import get_amazon_metadata
from openlibrary.core.wikidata import WikidataEntity, get_wikidata_entity
from openlibrary.plugins.upstream.utils import get_identifier_config
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.utils.isbn import canonical, isbn_13_to_isbn_10, to_isbn_13

from ..accounts import OpenLibraryAccount  # noqa: F401 side effects may be needed
from ..plugins.upstream.utils import get_coverstore_public_url, get_coverstore_url
from . import cache, waitinglist
from .ia import get_metadata
from .waitinglist import WaitingLoan

SubjectType = Literal["subject", "place", "person", "time"]

logger = logging.getLogger("openlibrary.core")


def _get_ol_base_url() -> str:
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

    def info(self, fetch_author: bool = True) -> dict[str, Any] | None:
        url = f'{get_coverstore_url()}/{self.category}/id/{self.id}.json'
        if url.startswith("//"):
            url = "http:" + url
        try:
            d = requests.get(url).json()
            d['created'] = parse_datetime(d['created'])
            if fetch_author:
                if d['author'] == 'None':
                    d['author'] = None
                d['author'] = d['author'] and self._site.get(d['author'])

            return web.storage(d)
        except OSError:
            # coverstore is down
            return None

    def get_aspect_ratio(self) -> float | None:
        info = self.info(fetch_author=False)
        if info and info.get('width') and info.get('height'):
            return info["width"] / info["height"]
        return None

    def url(self, size="M") -> str:
        """Get the public URL of the image."""
        coverstore_url = get_coverstore_public_url()
        return f"{coverstore_url}/{self.category}/id/{self.id}-{size.upper()}.jpg"

    def __repr__(self):
        return "<image: %s/%d>" % (self.category, self.id)


ThingKey = str


class Thing(client.Thing):
    """Base class for all OL models."""

    key: ThingKey

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
            v.created = parse_datetime(v.created)
            v.author = v.author and self._site.get(v.author, lazy=True)
            return v

        history.initial = [process(v) for v in history.initial]
        history.recent = [process(v) for v in history.recent]

        return history

    @cache.memoize(engine="memcache", key=lambda self: ("d" + self.key, "h"))
    def _get_history_preview(self) -> dict[str, list[dict]]:
        h = {}
        if self.revision < 5:
            h['recent'] = self._get_versions(limit=5)
            h['initial'] = h['recent'][-1:]
            h['recent'] = h['recent'][:-1]
        else:
            h['initial'] = self._get_versions(limit=1, offset=self.revision - 1)
            h['recent'] = self._get_versions(limit=4)
        return h

    def _get_versions(self, limit: int, offset: int = 0) -> list[dict]:
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

    def prefetch(self) -> None:
        """Prefetch all the anticipated data."""
        preview = self.get_history_preview()
        authors = {v.author.key for v in preview.initial + preview.recent if v.author}
        # preload them
        self._site.get_many(list(authors))

    def _make_url(
        self, label: str | None, suffix: str, relative: bool = True, **params
    ) -> str:
        """Make url of the form $key/$label$suffix?$params."""
        if label is not None:
            u = self.key + "/" + urlsafe(label) + suffix
        else:
            u = self.key + suffix
        if params:
            u += '?' + urlencode(params)
        if not relative:
            u = _get_ol_base_url() + u
        return u

    def get_url(self, suffix: str = "", **params) -> str:
        """Constructs a URL for this page with given suffix and query params.

        The suffix is added to the URL of the page and query params are appended after adding "?".
        """
        return self._make_url(label=self.get_url_suffix(), suffix=suffix, **params)

    def get_url_suffix(self) -> str | None:
        """Returns the additional suffix that is added to the key to get the URL of the page.

        Models of Edition, Work etc. should extend this to return the suffix.

        This is used to construct the URL of the page. By default URL is the
        key of the page. If this method returns None, nothing is added to the
        key. If this method returns a string, it is sanitized and added to key
        after adding a "/".
        """
        return None

    def _get_lists(self, limit: int = 50, offset: int = 0, sort: bool = True):
        # cache the default case
        if limit == 50 and offset == 0:
            keys = self._get_lists_cached()
        else:
            keys = self._get_lists_uncached(limit=limit, offset=offset)

        lists = self._site.get_many(keys)
        if sort:
            lists = safesort(lists, reverse=True, key=lambda list: list.last_modified)
        return lists

    @cache.memoize(engine="memcache", key=lambda self: ("d" + self.key, "l"))
    def _get_lists_cached(self):
        return self._get_lists_uncached(limit=50, offset=0)

    def _get_lists_uncached(self, limit: int, offset: int) -> list[str]:
        q = {
            "type": "/type/list",
            "seeds": {"key": self.key},
            "limit": limit,
            "offset": offset,
        }
        return self._site.things(q)

    def _get_d(self) -> dict:
        """Returns the data that goes into memcache as d/$self.key.
        Used to measure the memcache usage.
        """
        return {
            "h": self._get_history_preview(),
            "l": self._get_lists_cached(),
        }


class ThingReferenceDict(TypedDict):
    key: ThingKey


class Edition(Thing):
    """Class to represent /type/edition objects in OL."""

    table_of_contents: list[dict] | list[str] | list[str | dict] | None
    """
    Should be a list of dict; the other types are legacy
    """

    def url(self, suffix="", **params):
        return self.get_url(suffix, **params)

    def get_url_suffix(self) -> str:
        return self.title or "untitled"

    def __repr__(self):
        return "<Edition: %s>" % repr(self.title)

    __str__ = __repr__

    def full_title(self):
        # retained for backward-compatibility. Is anybody using this really?
        return self.title

    def get_publish_year(self) -> int | None:
        if self.publish_date:
            m = web.re_compile(r"(\d\d\d\d)").search(self.publish_date)
            return m and int(m.group(1))
        return None

    def get_lists(self, limit: int = 50, offset: int = 0, sort: bool = True):
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
                d['read_url'] = f"https://archive.org/stream/{self.ocaid}"
                d['daisy_only'] = False
        return d

    def get_ia_collections(self):
        return self.get_ia_meta_fields().get("collection", [])

    def is_access_restricted(self) -> bool:
        collections = self.get_ia_collections()
        return bool(collections) and (
            'printdisabled' in collections
            or self.get_ia_meta_fields().get("access-restricted") is True
        )

    def is_in_private_collection(self) -> bool:
        """Private collections are lendable books that should not be
        linked/revealed from OL
        """
        return private_collection_in(self.get_ia_collections())

    def in_borrowable_collection(self) -> bool:
        collections = self.get_ia_collections()
        return ('inlibrary' in collections) and not self.is_in_private_collection()

    def get_waitinglist(self) -> list[WaitingLoan]:
        """Returns list of records for all users currently waiting for this book."""
        return waitinglist.get_waitinglist_for_book(self.key)

    @property  # type: ignore[misc]
    def ia_metadata(self) -> dict:
        ocaid = self.get('ocaid')
        return get_metadata(ocaid) if ocaid else {}

    def get_waitinglist_size(self) -> int:
        """Returns the number of people on waiting list to borrow this book."""
        return waitinglist.get_waitinglist_size(self.key)

    def get_loans(self):
        from ..plugins.upstream import borrow  # noqa: PLC0415

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

    @staticmethod
    def get_isbn_or_asin(isbn_or_asin: str) -> tuple[str, str]:
        """
        Return a tuple with an ISBN or an ASIN, accompanied by an empty string.
        If the identifier is an ISBN, it appears in index 0.
        If the identifier is an ASIN, it appears in index 1.
        """
        isbn = canonical(isbn_or_asin)
        asin = isbn_or_asin.upper() if isbn_or_asin.upper().startswith("B") else ""
        return (isbn, asin)

    @staticmethod
    def is_valid_identifier(isbn: str, asin: str) -> bool:
        """Return `True` if there is a valid identifier."""
        return len(isbn) in [10, 13] or len(asin) == 10

    @staticmethod
    def get_identifier_forms(isbn: str, asin: str) -> list[str]:
        """Make a list of ISBN 10, ISBN 13, and ASIN, insofar as each is available."""
        isbn_13 = to_isbn_13(isbn)
        isbn_10 = isbn_13_to_isbn_10(isbn_13) if isbn_13 else None
        return [id_ for id_ in [isbn_10, isbn_13, asin] if id_]

    @classmethod
    def from_isbn(
        cls, isbn_or_asin: str, high_priority: bool = False
    ) -> "Edition | None":
        """
        Attempts to fetch an edition by ISBN or ASIN, or if no edition is found, then
        check the import_item table for a match, then as a last result, attempt
        to import from Amazon.
        :param bool high_priority: If `True`, (1) any AMZ import requests will block
                until AMZ has fetched data, and (2) the AMZ request will go to
                the front of the queue. If `False`, the import will simply be
                queued up if the item is not in the AMZ cache, and the affiliate
                server will return a promise.
        :return: an open library edition for this ISBN or None.
        """
        # Determine if we've got an ISBN or ASIN and if it's facially valid.
        isbn, asin = cls.get_isbn_or_asin(isbn_or_asin)
        if not cls.is_valid_identifier(isbn=isbn, asin=asin):
            return None

        # Create a list of ISBNs (or an ASIN) to match.
        if not (book_ids := cls.get_identifier_forms(isbn=isbn, asin=asin)):
            return None

        # Attempt to fetch book from OL
        for book_id in book_ids:
            if book_id == asin:
                query = {"type": "/type/edition", 'identifiers': {'amazon': asin}}
            else:
                query = {"type": "/type/edition", f'isbn_{len(book_id)}': book_id}

            if matches := web.ctx.site.things(query):
                return web.ctx.site.get(matches[0])

        # Attempt to fetch the book from the import_item table
        if edition := ImportItem.import_first_staged(identifiers=book_ids):
            return edition

        # Finally, try to fetch the book data from Amazon + import.
        # If `high_priority=True`, then the affiliate-server, which `get_amazon_metadata()`
        # uses, will block + wait until the Product API responds and the result, if any,
        # is staged in `import_item`.
        try:
            id_ = asin or book_ids[0]
            id_type = "asin" if asin else "isbn"
            get_amazon_metadata(id_=id_, id_type=id_type, high_priority=high_priority)
            return ImportItem.import_first_staged(identifiers=book_ids)
        except requests.exceptions.ConnectionError:
            logger.exception("Affiliate Server unreachable")
        except requests.exceptions.HTTPError:
            logger.exception(f"Affiliate Server: id {id_} not found")
        return None

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

    def get_users_rating(self, username: str) -> int | None:
        if not username:
            return None
        work_id = extract_numeric_id_from_olid(self.key)
        rating = Ratings.get_users_rating_for_work(username, work_id)
        return rating

    def get_patrons_who_also_read(self):
        key = self.key.split('/')[-1][2:-1]
        return Bookshelves.patrons_who_also_read(key)

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

    def get_awards(self) -> list:
        if not self.key:
            return []

        work_id = extract_numeric_id_from_olid(self.key)
        return Bestbook.get_awards(work_id)

    def check_if_user_awarded(self, username) -> bool:
        if not self.key:
            return False
        work_id = extract_numeric_id_from_olid(self.key)
        return bool(Bestbook.get_awards(username=username, work_id=work_id))

    def get_award_by_username(self, username):
        if not self.key:
            return None
        work_id = extract_numeric_id_from_olid(self.key)
        awards = Bestbook.get_awards(username=username, work_id=work_id)
        return awards[0] if awards else None

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

    def get_subject_links(self, type: SubjectType = "subject"):
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

    @classmethod
    def resolve_redirect_chain(
        cls, work_key: str, test: bool = False
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {
            'key': work_key,
            'redirect_chain': [],
            'resolved_key': None,
            'modified': False,
        }
        redirect_chain = cls.get_redirect_chain(work_key)
        summary['redirect_chain'] = [
            {"key": thing.key, "occurrences": {}, "updates": {}}
            for thing in redirect_chain
        ]
        summary['resolved_key'] = redirect_chain[-1].key

        for r in summary['redirect_chain']:
            olid = r['key'].split('/')[-1][2:-1]  # 'OL1234x' --> '1234'
            new_olid = summary['resolved_key'].split('/')[-1][2:-1]

            # count reading log entries
            r['occurrences']['readinglog'] = len(Bookshelves.get_works_shelves(olid))
            r['occurrences']['ratings'] = len(Ratings.get_all_works_ratings(olid))
            r['occurrences']['booknotes'] = len(Booknotes.get_booknotes_for_work(olid))
            r['occurrences']['bestbooks'] = Bestbook.get_count(work_id=olid)
            r['occurrences']['observations'] = len(
                Observations.get_observations_for_work(olid)
            )

            if new_olid != olid:
                # track updates
                r['updates']['readinglog'] = Bookshelves.update_work_id(
                    olid, new_olid, _test=test
                )
                r['updates']['ratings'] = Ratings.update_work_id(
                    olid, new_olid, _test=test
                )
                r['updates']['booknotes'] = Booknotes.update_work_id(
                    olid, new_olid, _test=test
                )
                r['updates']['observations'] = Observations.update_work_id(
                    olid, new_olid, _test=test
                )
                r['updates']['bestbooks'] = Bestbook.update_work_id(
                    olid, new_olid, _test=test
                )
                summary['modified'] = summary['modified'] or any(
                    any(r['updates'][group].values())
                    for group in [
                        'readinglog',
                        'ratings',
                        'booknotes',
                        'observations',
                        'bestbooks',
                    ]
                )

        return summary

    @classmethod
    def get_redirects(cls, day, batch_size=1000, batch=0):
        tomorrow = day + timedelta(days=1)

        work_redirect_ids = web.ctx.site.things(
            {
                "type": "/type/redirect",
                "key~": "/works/*",
                "limit": batch_size,
                "offset": (batch * batch_size),
                "sort": "-last_modified",
                "last_modified>": day.strftime('%Y-%m-%d'),
                "last_modified<": tomorrow.strftime('%Y-%m-%d'),
            }
        )
        more = len(work_redirect_ids) == batch_size
        logger.info(
            f"[update-redirects] batch: {batch}, size {batch_size}, offset {batch * batch_size}, more {more}, len {len(work_redirect_ids)}"
        )
        return work_redirect_ids, more

    @classmethod
    def resolve_redirects_bulk(
        cls,
        days: int = 1,
        batch_size: int = 1000,
        grace_period_days: int = 7,
        cutoff_date: datetime = datetime(year=2017, month=1, day=1),
        test: bool = False,
    ):
        """
        batch_size - how many records to fetch per batch
        start_offset - what offset to start from
        grace_period_days - ignore redirects created within period of days
        cutoff_date - ignore redirects created before this date
        test - don't resolve stale redirects, just identify them
        """
        fixed = 0
        total = 0
        current_date = datetime.today() - timedelta(days=grace_period_days)
        cutoff_date = (current_date - timedelta(days)) if days else cutoff_date

        while current_date > cutoff_date:
            has_more = True
            batch = 0
            while has_more:
                logger.info(
                    f"[update-redirects] {current_date}, batch {batch+1}: #{total}",
                )
                work_redirect_ids, has_more = cls.get_redirects(
                    current_date, batch_size=batch_size, batch=batch
                )
                work_redirect_batch = web.ctx.site.get_many(work_redirect_ids)
                for work in work_redirect_batch:
                    total += 1
                    chain = Work.resolve_redirect_chain(work.key, test=test)
                    if chain['modified']:
                        fixed += 1
                        logger.info(
                            f"[update-redirects] {current_date}, Update: #{total} fix#{fixed} batch#{batch} <{work.key}> {chain}"
                        )
                    else:
                        logger.info(
                            f"[update-redirects] No Update Required: #{total} <{work.key}>"
                        )
                batch += 1
            current_date = current_date - timedelta(days=1)

        logger.info(f"[update-redirects] Done, processed {total}, fixed {fixed}")


class AuthorRemoteIdConflictError(ValueError):
    pass


class Author(Thing):
    """Class to represent /type/author objects in OL."""

    def url(self, suffix="", **params):
        return self.get_url(suffix, **params)

    def get_url_suffix(self):
        return self.name or "unnamed"

    def wikidata(
        self, bust_cache: bool = False, fetch_missing: bool = False
    ) -> WikidataEntity | None:
        if wd_id := self.remote_ids.get("wikidata"):
            return get_wikidata_entity(
                qid=wd_id, bust_cache=bust_cache, fetch_missing=fetch_missing
            )
        return None

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

    def merge_remote_ids(
        self, incoming_ids: dict[str, str]
    ) -> tuple[dict[str, str], int]:
        """Returns the author's remote IDs merged with a given remote IDs object, as well as a count for how many IDs had conflicts.
        If incoming_ids is empty, or if there are more conflicts than matches, no merge will be attempted, and the output will be (author.remote_ids, -1).
        """
        output = {**self.remote_ids}
        if not incoming_ids:
            return output, -1
        # Count
        matches = 0
        config = get_identifier_config("author")
        for id in config["identifiers"]:
            identifier: str = id.name
            if identifier in output and identifier in incoming_ids:
                if output[identifier] != incoming_ids[identifier]:
                    # For now, cause an error so we can see when/how often this happens
                    raise AuthorRemoteIdConflictError(
                        f"Conflicting remote IDs for author {self.key}: {output[identifier]} vs {incoming_ids[identifier]}"
                    )
                else:
                    matches = matches + 1
        return output, matches


class User(Thing):
    def get_default_preferences(self) -> dict[str, str]:
        return {'update': 'no', 'public_readlog': 'no', 'type': 'preferences'}
        # New users are now public by default for new patrons
        # As of 2020-05, OpenLibraryAccount.create will
        # explicitly set public_readlog: 'yes'.
        # Legacy accounts w/ no public_readlog key
        # will continue to default to 'no'

    def get_usergroups(self):
        keys = self._site.things({'type': '/type/usergroup', 'members': self.key})
        return self._site.get_many(keys)

    usergroups = property(get_usergroups)

    def get_account(self):
        username = self.get_username()
        return accounts.find(username=username)

    def get_email(self) -> str | None:
        account = self.get_account() or {}
        return account.get("email")

    def get_username(self) -> str:
        return self.key.split("/")[-1]

    def preferences(self, use_store: bool = False):
        key = f"{self.key}/preferences"
        if use_store:
            prefs = web.ctx.site.store.get(key)
            return prefs or self.get_default_preferences()

        prefs = web.ctx.site.get(key)
        return (
            prefs and prefs.dict().get('notifications')
        ) or self.get_default_preferences()

    def save_preferences(
        self, new_prefs, msg='updating user preferences', use_store: bool = False
    ) -> None:
        key = f'{self.key}/preferences'
        if use_store:
            old_prefs = self.preferences(use_store=use_store)
            old_prefs.update(new_prefs)
            old_prefs['_rev'] = None
            old_prefs['type'] = 'preferences'
            web.ctx.site.store[key] = old_prefs
        else:
            old_prefs = web.ctx.site.get(key)
            prefs = (old_prefs and old_prefs.dict()) or {
                'key': key,
                'type': {'key': '/type/object'},
            }
            if 'notifications' not in prefs:
                prefs['notifications'] = self.get_default_preferences()
            prefs['notifications'].update(new_prefs)
            web.ctx.site.save(prefs, msg)
            # Save a copy of the patron's preferences to the store
            self.save_preferences(new_prefs, msg=msg, use_store=True)

    def is_usergroup_member(self, usergroup: str) -> bool:
        if not usergroup.startswith('/usergroup/'):
            usergroup = f'/usergroup/{usergroup}'
        return usergroup in [g.key for g in self.usergroups]

    def is_subscribed_user(self, username: str) -> int:
        my_username = self.get_username()
        return (
            PubSub.is_subscribed(my_username, username)
            if my_username != username
            else -1
        )

    def has_cookie(self, name):
        return web.cookies().get(name, False)

    def is_printdisabled(self):
        return web.cookies().get('pd')

    def is_admin(self) -> bool:
        return self.is_usergroup_member('/usergroup/admin')

    def is_librarian(self) -> bool:
        return self.is_usergroup_member('/usergroup/librarians')

    def is_super_librarian(self) -> bool:
        return self.is_usergroup_member('/usergroup/super-librarians')

    def is_beta_tester(self) -> bool:
        return self.is_usergroup_member('/usergroup/beta-testers')

    def is_read_only(self) -> bool:
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
            lists = safesort(lists, reverse=True, key=lambda list: list.last_modified)
        return lists

    @classmethod
    # @cache.memoize(engine="memcache", key="user-avatar")
    def get_avatar_url(cls, username: str) -> str:
        username = username.split('/people/')[-1]
        user = web.ctx.site.get(f'/people/{username}')
        itemname = user.get_account().get('internetarchive_itemname')

        return f'https://archive.org/services/img/{itemname}'

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

    def new_list(self, name: str, description: str, seeds, tags=None):
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

    def get_waitinglist(self):
        """Returns list of records for all the books the user is currently waiting for."""
        return waitinglist.get_waitinglist_for_user(self.key)

    def has_borrowed(self, book):
        """Returns True if this user has borrowed given book."""
        loan = self.get_loan_for(book.ocaid)
        return loan is not None

    def get_loan_for(self, ocaid, use_cache=False):
        """Returns the loan object for given ocaid.

        Returns None if this user hasn't borrowed the given book.
        """
        from ..plugins.upstream import borrow  # noqa: F401, PLC0415

        loans = (
            lending.get_cached_loans_of_user(self.key)
            if use_cache
            else lending.get_loans_of_user(self.key)
        )
        for loan in loans:
            if ocaid == loan['ocaid']:
                return loan

    def get_waiting_loan_for(self, ocaid):
        """
        :param str or None ocaid: edition ocaid
        :rtype: dict (e.g. {position: number})
        """
        return ocaid and WaitingLoan.find(self.key, ocaid)

    def get_user_waiting_loans(self, ocaid=None, use_cache=False):
        """
        Similar to get_waiting_loan_for, but fetches and caches all of user's waiting loans
        :param str or None ocaid: edition ocaid
        :rtype: dict (e.g. {position: number})
        """
        all_user_waiting_loans = (
            lending.get_cached_user_waiting_loans
            if use_cache
            else lending.get_user_waiting_loans
        )(self.key)
        if ocaid:
            return next(
                (
                    loan
                    for loan in all_user_waiting_loans
                    if loan['identifier'] == ocaid
                ),
                None,
            )
        return all_user_waiting_loans

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
            extra_attrs += f'class="{cls}" '
        # Why nofollow?
        return f'<a rel="nofollow" href="{self.key}" {extra_attrs}>{web.net.htmlquote(self.displayname)}</a>'

    def set_data(self, data):
        self._data = data
        self._save()


class UserGroup(Thing):
    @classmethod
    def from_key(cls, key: str):
        """
        :param str key: e.g. /usergroup/foo
        :rtype: UserGroup | None
        """
        if not key.startswith('/usergroup/'):
            key = f"/usergroup/{key}"
        return web.ctx.site.get(key)

    def add_user(self, userkey: str) -> None:
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
    key: str
    name: str
    subject_type: str
    solr_query: str
    """Query with normalized subject key to get matching books; eg 'person_key:ned_wilcox'"""

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
            lists = safesort(lists, reverse=True, key=lambda list: list.last_modified)
        return lists

    def get_seed(self):
        seed = self.key.split("/")[-1]
        if seed.split(":")[0] not in ["place", "person", "time"]:
            seed = "subject:" + seed
        return seed

    def url(self, suffix="", relative=True, **params):
        u = self.key + suffix
        if params:
            u += '?' + urlencode(params)
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


class Tag(Thing):
    """Class to represent /type/tag objects in OL."""

    def url(self, suffix="", **params):
        return self.get_url(suffix, **params)

    def get_url_suffix(self):
        return self.name or "unnamed"

    @classmethod
    def find(cls, tag_name, tag_type=None):
        """Returns a list of keys for Tags that match the search criteria."""
        q = {'type': '/type/tag', 'name': tag_name}
        if tag_type:
            q['tag_type'] = tag_type
        matches = list(web.ctx.site.things(q))
        return matches

    @classmethod
    def create(
        cls,
        tag,
        ip='127.0.0.1',
        comment='New Tag',
    ):
        """Creates a new Tag object."""
        current_user = web.ctx.site.get_user()
        patron = current_user.get_username() if current_user else 'ImportBot'
        key = web.ctx.site.new_key('/type/tag')
        tag['key'] = key

        from openlibrary.accounts import RunAs  # noqa: PLC0415

        with RunAs(patron):
            web.ctx.ip = web.ctx.ip or ip
            t = web.ctx.site.save(
                tag,
                comment=comment,
            )
            return t


@dataclass
class LoggedBooksData:
    """
    LoggedBooksData contains data used for displaying a page of the reading log, such
    as the page size for pagination, the docs returned from the reading log DB for
    a particular shelf, query, sorting, etc.

    param page_size specifies how many results per page should display in the
        reading log.
    param shelf_totals holds the counts for books on the three default shelves.
    param docs holds the documents returned from Solr.
    param q holds an optional query string (len >= 3, per my_books_view in mybooks.py)
        for filtering the reading log.
    param ratings holds a list of ratings such that the index of each rating corresponds
        to the index of each doc/work in self.docs.
    """

    username: str
    page_size: int
    total_results: int
    shelf_totals: dict[int, int]
    docs: list[web.storage]
    q: str = ""
    ratings: list[int] = field(default_factory=list)

    def load_ratings(self) -> None:
        """
        Load the ratings into self.ratings from the storage docs, such that the index
        of each returned rating corresponds to the index of each web storage doc. This
        allows them to be zipped together if needed. E.g. in a template.

        The intent of this is so that there is no need to query ratings from the
        template, as the docs and ratings are together when needed.
        """
        for doc in self.docs:
            work_id = extract_numeric_id_from_olid(doc.key)
            rating = Ratings.get_users_rating_for_work(self.username, work_id)
            self.ratings.append(rating or 0)


def register_models():
    client.register_thing_class(None, Thing)  # default
    client.register_thing_class('/type/edition', Edition)
    client.register_thing_class('/type/work', Work)
    client.register_thing_class('/type/author', Author)
    client.register_thing_class('/type/user', User)
    client.register_thing_class('/type/usergroup', UserGroup)
    client.register_thing_class('/type/tag', Tag)


def register_types():
    """Register default types for various path patterns used in OL."""
    from infogami.utils import types  # noqa: PLC0415

    types.register_type('^/authors/[^/]*$', '/type/author')
    types.register_type('^/books/[^/]*$', '/type/edition')
    types.register_type('^/works/[^/]*$', '/type/work')
    types.register_type('^/languages/[^/]*$', '/type/language')
    types.register_type('^/tags/[^/]*$', '/type/tag')

    types.register_type('^/usergroup/[^/]*$', '/type/usergroup')
    types.register_type('^/permission/[^/]*$', '/type/permission')

    types.register_type('^/(css|js)/[^/]*$', '/type/rawtext')
