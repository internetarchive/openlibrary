"""Models of various OL objects.
"""
import urllib, urllib2
import simplejson
import web
import re

from psycopg2 import IntegrityError
import iptools
from infogami.infobase import client

import helpers as h

#TODO: fix this. openlibrary.core should not import plugins.
from openlibrary import accounts
from openlibrary.plugins.upstream.utils import get_history
from openlibrary.plugins.upstream.account import Account
from openlibrary.core.helpers import private_collection_in

# relative imports
from lists.model import ListMixin, Seed
from . import db, cache, iprange, inlibrary, loanstats, waitinglist, lending

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
        url = '%s/%s/id/%s.json' % (h.get_coverstore_url(), self.category, self.id)
        if url.startswith("//"):
            url = "http:" + url
        try:
            d = simplejson.loads(urllib2.urlopen(url).read())
            d['created'] = h.parse_datetime(d['created'])
            if d['author'] == 'None':
                d['author'] = None
            d['author'] = d['author'] and self._site.get(d['author'])

            return web.storage(d)
        except IOError:
            # coverstore is down
            return None

    def url(self, size="M"):
        return "%s/%s/id/%s-%s.jpg" % (h.get_coverstore_url(), self.category, self.id, size.upper())

    def __repr__(self):
        return "<image: %s/%d>" % (self.category, self.id)

class Thing(client.Thing):
    """Base class for all OL models."""

    @cache.method_memoize
    def get_history_preview(self):
        """Returns history preview.
        """
        history = self._get_history_preview()
        history = web.storage(history)

        history.revision = self.revision
        history.lastest_revision = self.revision
        history.created = self.created

        def process(v):
            """Converts entries in version dict into objects.
            """
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
            h['initial'] = self._get_versions(limit=1, offset=self.revision-1)
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
        """Returns the most recent change.
        """
        preview = self.get_history_preview()
        if preview.recent:
            return preview.recent[0]
        else:
            return preview.initial[0]

    def prefetch(self):
        """Prefetch all the anticipated data."""
        preview = self.get_history_preview()
        authors = set(v.author.key for v in preview.initial + preview.recent if v.author)
        # preload them
        self._site.get_many(list(authors))

    def _make_url(self, label, suffix, relative=True, **params):
        """Make url of the form $key/$label$suffix?$params.
        """
        if label is not None:
            u = self.key + "/" + h.urlsafe(label) + suffix
        else:
            u = self.key + suffix
        if params:
            u += '?' + urllib.urlencode(params)
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
            "offset": offset
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
    """Class to represent /type/edition objects in OL.
    """
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
            m = web.re_compile("(\d\d\d\d)").search(self.publish_date)
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
        return ('printdisabled' in collections
                or 'lendinglibrary' in collections
                or self.get_ia_meta_fields().get("access-restricted") is True)

    def is_in_private_collection(self):
        """Private collections are lendable books that should not be
        linked/revealed from OL
        """
        return private_collection_in(self.get_ia_collections())

    def in_borrowable_collection(self):
        collections = self.get_ia_collections()
        return ('lendinglibrary' in collections or
            ('inlibrary' in collections and inlibrary.get_library() is not None)
            ) and not self.is_in_private_collection()

    def can_borrow(self):
        """This method should be deprecated in favor of in_borrowable_collection"""
        return self.in_borrowable_collection()

    def get_waitinglist(self):
        """Returns list of records for all users currently waiting for this book."""
        return waitinglist.get_waitinglist_for_book(self.key)

    def get_realtime_availability(self):
        return lending.get_realtime_availability_of_ocaid(self.get('ocaid'))

    def get_waitinglist_size(self, ia=False):
        """Returns the number of people on waiting list to borrow this book.
        """
        return waitinglist.get_waitinglist_size(self.key)

    def get_waitinglist_position(self, user):
        """Returns the position of this user in the waiting list."""
        return waitinglist.get_waitinglist_position(user.key, self.key)

    def get_scanning_contributor(self):
        return self.get_ia_meta_fields().get("contributor")

    def get_loans(self):
        from ..plugins.upstream import borrow
        return borrow.get_edition_loans(self)

    def get_ebook_status(self):
        """
            None
            "read-online"
            "borrow-available"
            "borrow-checkedout"
            "borrow-user-checkedout"
            "borrow-user-waiting"
            "protected"
        """
        if self.get("ocaid"):
            if not self.is_access_restricted():
                return "read-online"
            if not self.is_lendable_book():
                return "protected"

            if self.get_available_loans():
                return "borrow-available"

            user = web.ctx.site.get_user()
            if not user:
                return "borrow-checkedout"

            checkedout_by_user = any(loan.get('user') == user.key for loan in self.get_current_loans())
            if checkedout_by_user:
                return "borrow-user-checkedout"
            if user.is_waiting_for(self):
                return "borrow-user-waiting"
            else:
                return "borrow-checkedout"

    def is_lendable_book(self):
        """Returns True if the book is lendable.
        """
        return self.in_borrowable_collection()

    def get_ia_download_link(self, suffix):
        """Returns IA download link for given suffix.
        The suffix is usually one of '.pdf', '.epub', '.mobi', '_djvu.txt'
        """
        if self.ocaid:
            metadata = self.get_ia_meta_fields()
            # The _filenames field is set by ia.get_metadata function
            filenames = metadata.get("_filenames")
            if filenames:
                filename = some(f for f in filenames if f.endswith(suffix))
            else:
                # filenames is not in cache.
                # This is required only until all the memcache entries expire
                filename = self.ocaid + suffix

            if filename is None and self.is_ia_scan():
                # IA scans will have all the required suffixes.
                # Sometimes they are generated on the fly.
                filename = self.ocaid + suffix

            if filename:
                return "https://archive.org/download/%s/%s" % (self.ocaid, filename)

    def is_ia_scan(self):
        metadata = self.get_ia_meta_fields()
        # all IA scans will have scanningcenter field set
        return bool(metadata.get("scanningcenter"))

def some(values):
    """Returns the first value that is True from the values iterator.
    Works like any, but returns the value instead of bool(value).
    Returns None if none of the values is True.
    """
    for v in values:
        if v:
            return v

class Bookshelves(object):

    PRESET_BOOKSHELVES = {
        'Want to Read': 1,
        'Currently Read': 2,
        'Already Read': 3
    }

    @classmethod
    def count_users_reads(cls, username, bookshelf_id=None):
        oldb = db.get_db()
        data = {'username': username}
        bookshelf_ids = ','.join([str(x) for x in cls.PRESET_BOOKSHELVES.values()])
        query = ("SELECT count(*) from bookshelves_books WHERE "
                 "bookshelf_id=ANY('{" + bookshelf_ids + "}'::int[]) "
                 "AND username=$username")
        if bookshelf_id:
            data['bookshelf_id'] = bookshelf_id
            query += ' AND bookshelf_id=$bookshelf_id'
        result = oldb.query(query, vars=data)
        return result[0]['count'] if result else 0

    @classmethod
    def get_users_reads(cls, username, bookshelf_id=None, limit=100, page=1):
        """Returns a list of books the user has, is, or wants to read
        """
        oldb = db.get_db()
        page = int(page) if page else 1
        offset = limit * (page - 1)
        data = {
            'username': username,
            'limit': limit,
            'offset': offset
        }
        bookshelf_ids = ','.join([str(x) for x in cls.PRESET_BOOKSHELVES.values()])
        query = ("SELECT * from bookshelves_books WHERE "
                 "bookshelf_id=ANY('{" + bookshelf_ids + "}'::int[]) "
                 "AND username=$username")
        if bookshelf_id:
            data['bookshelf_id'] = bookshelf_id
            query += ' AND bookshelf_id=$bookshelf_id'
        query += ' LIMIT $limit OFFSET $offset'
        return list(oldb.query(query, vars=data))

    @classmethod
    def get_users_read_status_of_work(cls, username, work_id):
        """A user can mark a book as (1) want to read, (2) currently reading,
        or (3) already read. Each of these states is mutually
        exclusive. Returns the user's read state of this work, if one
        exists.
        """
        oldb = db.get_db()
        data = {
            'username': username,
            'work_id': int(work_id)
        }
        bookshelf_ids = ','.join([str(x) for x in cls.PRESET_BOOKSHELVES.values()])
        query = ("SELECT bookshelf_id from bookshelves_books WHERE "
                 "bookshelf_id=ANY('{" + bookshelf_ids + "}'::int[]) "
                 "AND username=$username AND work_id=$work_id")
        result = list(oldb.query(query, vars=data))
        return result[0].bookshelf_id if result else None

    @classmethod
    def add(cls, username, bookshelf_id, work_id, edition_id=None, upsert=False):
        """Adds a book with `work_id` to user's bookshelf designated by
        `bookshelf_id`"""
        oldb = db.get_db()
        work_id = int(work_id)
        edition_id = int(edition_id) if edition_id else None
        bookself_id = int(bookshelf_id)
        data = {'work_id': work_id, 'username': username, 'edition_id': edition_id}

        users_status = cls.get_users_read_status_of_work(username, work_id)
        if not users_status:
            return oldb.insert('bookshelves_books', username=username,
                               bookshelf_id=bookshelf_id,
                               work_id=work_id, edition_id=edition_id)
        else:
            return oldb.update('bookshelves_books', where="work_id=$work_id AND username=$username",
                               bookshelf_id=bookshelf_id, vars=data)

    @classmethod
    def remove(cls, username, bookshelf_id, work_id, edition_id=None):
        oldb = db.get_db()
        try:
            return oldb.delete('bookshelves_books',
                               where=('work_id=$work_id AND username=$username'), vars={
                                   'username': username,
                                   'work_id': int(work_id),
                                   'edition_id': int(edition_id) if edition_id else None,
                                   'bookshelf_id': int(bookshelf_id)
                               })
        except:  # we want to catch no entry exists
            return None

    @classmethod
    def get_works_shelves(cls, work_id, lazy=False):
        """Bookshelves this work is on"""
        oldb = db.get_db()
        query = "SELECT * from bookshelves_books where work_id=$work_id"
        try:
            result = oldb.query(query, vars={'work_id': int(work_id)})
            return result if lazy else list(result)
        except:
            return None
        
class Ratings(object):

    @classmethod
    def register(cls, username, rating, work_id, edition_id=None):
        oldb = db.get_db()
        work_id = int(work_id)
        edition_id = int(edition_id) if edition_id else None
        rating = int(rating)
        data = {
            'username': username,
            'work_id': work_id,
            'edition_id': edition_id,
            'rating': rating
        }
        try:
            # XXX insert, update, or delete
            oldb.insert('ratings', username=username, work_id=work_id, edition_id=edition_id, rating=rating)
            #oldb.delete('ratings',
            #                where=('work_id=$work_id AND username=$username'), vars=data)
        except:  # we want to except entry already exists or no entry exists
            # log
            pass
        url = ('/books/OL%sM' % edition_id) if edition_id else ('/works/OL%sW' % work_id)
        raise web.seeother(url)

    @classmethod
    def get_users_ratings(cls, username):
        oldb = db.get_db()
        return [x.work_id for x in oldb.select('ratings', where="username=$username",
                           vars={'username': username})]

    @classmethod
    def get_most_rated_works(cls):
        pass

    @classmethod
    def count(cls, work_id, username=None, edition_id=None):
        """Retrieves a count of likes for a work (or a specific edition of a work"""
        oldb = db.get_db()
        work_id = int(work_id)
        query = 'SELECT COUNT(*) AS work_ratings_count FROM ratings where ratings.work_id=$work_id'
        if username:
            query = "SELECT (SELECT COUNT(*) FROM ratings where ratings.work_id=$work_id) AS work_ratings_count, (SELECT EXISTS(SELECT 1 FROM ratings where ratings.username=$username AND ratings.work_id=$work_id)) AS user_rated_work"
        return oldb.query(query, vars={'work_id': work_id, 'username': username})[0]

class Likes(object):

    @classmethod
    def register(cls, username, work_id, edition_id=None, like=True):
        oldb = db.get_db()
        work_id = int(work_id)
        edition_id = int(edition_id) if edition_id else None
        data = {
            'username': username,
            'work_id': work_id,
            'edition_id': edition_id
        }
        try:
            if like:
                oldb.insert('likes', username=username, work_id=work_id, edition_id=edition_id)
            else:
                oldb.delete('likes',
                            where=('work_id=$work_id AND username=$username'), vars=data)
        except:  # we want to except entry already exists or no entry exists
            # log
            pass
        url = ('/books/OL%sM' % edition_id) if edition_id else ('/works/OL%sW' % work_id)
        raise web.seeother(url)

    @classmethod
    def get_users_likes(cls, username):
        oldb = db.get_db()
        return [x.work_id for x in oldb.select('likes', where="username=$username",
                           vars={'username': username})]

    @classmethod
    def count(cls, work_id, username=None, edition_id=None):
        """Retrieves a count of likes for a work (or a specific edition of a work"""
        oldb = db.get_db()
        work_id = int(work_id)
        query = 'SELECT COUNT(*) AS work_likes_count FROM likes where likes.work_id=$work_id'
        if username:
            query = "SELECT (SELECT COUNT(*) FROM likes where likes.work_id=$work_id) AS work_likes_count, (SELECT EXISTS(SELECT 1 FROM likes where likes.username=$username AND likes.work_id=$work_id)) AS user_likes_work"
        return oldb.query(query, vars={'work_id': work_id, 'username': username})[0]

class Work(Thing):
    """Class to represent /type/work objects in OL.
    """
    def url(self, suffix="", **params):
        return self.get_url(suffix, **params)

    def get_url_suffix(self):
        return self.title or "untitled"

    def __repr__(self):
        return "<Work: %s>" % repr(self.key)
    __str__ = __repr__

    @property
    @cache.method_memoize
    @cache.memoize(engine="memcache", key=lambda self: ("d" + self.key, "e"))
    def edition_count(self):
        return self._site._request("/count_editions_by_work", data={"key": self.key})

    def get_one_edition(self):
        """Returns any one of the editions.

        Used to get the only edition when edition_count==1.
        """
        # If editions from solr are available, use that.
        # Otherwise query infobase to get the editions (self.editions makes infobase query).
        editions = self.get_sorted_editions() or self.editions
        return editions and editions[0] or None

    def get_lists(self, limit=50, offset=0, sort=True):
        return self._get_lists(limit=limit, offset=offset, sort=sort)

    def get_users_read_status(self, username):
        if not username:
            return None
        work_id = self.key.split('/')[2][2:-1]
        status_id = Bookshelves.get_users_read_status_of_work(username, work_id)
        return status_id

    def likes(self, username=None):
        work_id = self.key.split('/')[2][2:-1]
        return Likes.count(work_id, username=username)

    def _get_d(self):
        """Returns the data that goes into memcache as d/$self.key.
        Used to measure the memcache usage.
        """
        return {
            "h": self._get_history_preview(),
            "l": self._get_lists_cached(),
            "e": self.edition_count
        }

    def _make_subject_link(self, title, prefix=""):
        slug = web.safestr(title.lower().replace(' ', '_').replace(',',''))
        key = "/subjects/%s%s" % (prefix, slug)
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
            d['read_url'] = "https://archive.org/stream/{0}".format(solrdata.ia[0])
            d['has_ebook'] = True
        elif solrdata.get('lending_edition_s'):
            d['borrow_url'] = "/books/{0}/x/borrow".format(solrdata.lending_edition_s)
            #d['borrowed'] = solrdata.checked_out
            d['has_ebook'] = True
        if solrdata.get('ia'):
            d['ia'] = solrdata.get('ia')
        return d

class Author(Thing):
    """Class to represent /type/author objects in OL.
    """
    def url(self, suffix="", **params):
        return self.get_url(suffix, **params)

    def get_url_suffix(self):
        return self.name or "unnamed"

    def __repr__(self):
        return "<Author: %s>" % repr(self.key)
    __str__ = __repr__

    def get_edition_count(self):
        return self._site._request(
                '/count_editions_by_author',
                data={'key': self.key})
    edition_count = property(get_edition_count)

    def get_lists(self, limit=50, offset=0, sort=True):
        return self._get_lists(limit=limit, offset=offset, sort=sort)

class User(Thing):
    def get_status(self):
        account = self.get_account() or {}
        return account.get("status")

    def get_usergroups(self):
        keys = self._site.things({
            'type': '/type/usergroup',
            'members': self.key})
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

    def is_admin(self):
        return '/usergroup/admin' in [g.key for g in self.usergroups]

    def get_ratings(self):
        #work_olids = ['/works/OL%sW' % work_olid for work_olid in Likes.get_users_likes(self.get_username())]
        #works = web.ctx.site.get_many(work_olids)
        #return works
        pass

    def get_books_to_read(self):
        work_olids = ['/works/OL%sW' % work_olid for work_olid in Likes.get_users_likes(self.get_username())]
        works = web.ctx.site.get_many(work_olids)
        return works

    def get_reads_count(self, bookshelf_id=None):
        return Bookshelves.count_users_reads(self.get_username(), bookshelf_id=bookshelf_id)

    def get_reads(self, bookshelf_id=None, limit=100, page=1):
        """Returns a list of books this user has, is, or wants to read"""
        return Bookshelves.get_users_reads(self.get_username(), bookshelf_id=bookshelf_id,
                                           limit=limit, page=page)

    def get_likes(self):
        work_olids = ['/works/OL%sW' % work_olid for work_olid in Likes.get_users_likes(self.get_username())]
        works = web.ctx.site.get_many(work_olids)
        return works

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
            "offset": offset
        }
        if seed:
            if isinstance(seed, Thing):
                seed = {"key": seed.key}
            q['seeds'] = seed

        return self._site.things(q)

    def new_list(self, name, description, seeds, tags=[]):
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
        key = "%s/lists/OL%sL" % (self.key, id)
        doc = {
            "key": key,
            "type": {
                "key": "/type/list"
            },
            "name": name,
            "description": description,
            "seeds": seeds,
            "tags": tags
        }
        return self._site.new(key, doc)

    def is_waiting_for(self, book):
        """Returns True if this user is waiting to loan given book.
        """
        return waitinglist.is_user_waiting_for(self.key, book.key)

    def get_waitinglist(self):
        """Returns list of records for all the books the user is currently waiting for."""
        return waitinglist.get_waitinglist_for_user(self.key)

    def has_borrowed(self, book):
        """Returns True if this user has borrowed given book.
        """
        loan = self.get_loan_for(book)
        return loan is not None

    #def can_borrow_edition(edition, _type):


    def get_loan_for(self, book):
        """Returns the loan object for given book.

        Returns None if this user hasn't borrowed the given book.
        """
        from ..plugins.upstream import borrow
        loans = borrow.get_loans(self)
        for loan in loans:
            if book.key == loan['book'] or book.ocaid == loan['ocaid']:
                return loan

    def get_waiting_loan_for(self, book):
        return waitinglist.get_waiting_loan_object(self.key, book.key)

    def __repr__(self):
        return "<User: %s>" % repr(self.key)
    __str__ = __repr__

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
        """Returns a cover object.
        """
        return self.cover and Image(self._site, "b", self.cover)

    def get_tags(self):
        """Returns tags as objects.

        Each tag object will contain name and url fields.
        """
        return [web.storage(name=t, url=self.key + u"/tags/" + t) for t in self.tags]

    def _get_subjects(self):
        """Returns list of subjects inferred from the seeds.
        Each item in the list will be a storage object with title and url.
        """
        # sample subjects
        return [
            web.storage(title="Cheese", url="/subjects/cheese"),
            web.storage(title="San Francisco", url="/subjects/place:san_francisco")
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
        """Removes a seed for the list.
        """
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
        return "<List: %s (%r)>" % (self.key, self.name)

class Library(Thing):
    """Library document.

    Each library has a list of IP addresses belongs to that library.
    """
    def url(self, suffix="", **params):
        return self.get_url(suffix, **params)

    def find_bad_ip_ranges(self, text):
        return iprange.find_bad_ip_ranges(text)

    def parse_ip_ranges(self, text):
        return iprange.parse_ip_ranges(text)

    def get_ip_range_list(self):
        """Returns IpRangeList object for the range of IPs of this library.
        """
        ranges = list(self.parse_ip_ranges(self.ip_ranges or ""))
        return iptools.IpRangeList(*ranges)

    def has_ip(self, ip):
        """Return True if the the given ip is part of the library's ip range.
        """
        return ip in self.get_ip_range_list()

    def get_branches(self):
        # Library Name | Street | City | State | Zip | Country | Telephone | Website | Lat, Long
        columns = ["name", "street", "city", "state", "zip", "country", "telephone", "website", "latlong"]
        def parse(line):
            branch = web.storage(zip(columns, line.strip().split("|")))

            # add empty values for missing columns
            for c in columns:
                branch.setdefault(c, "")

            try:
                branch.lat, branch.lon = branch.latlong.split(",", 1)
            except ValueError:
                branch.lat = "0"
                branch.lon = "0"
            return branch
        return [parse(line) for line in self.addresses.splitlines() if line.strip()]

    def get_loans_per_day(self, resource_type="total"):
        name = self.key.split("/")[-1]
        stats = loanstats.LoanStats(library=name)
        return stats.get_loans_per_day(resource_type=resource_type)

class Subject(web.storage):
    def get_lists(self, limit=1000, offset=0, sort=True):
        q = {
            "type": "/type/list",
            "seeds": self.get_seed(),
            "limit": limit,
            "offset": offset
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
            u += '?' + urllib.urlencode(params)
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
    client.register_thing_class(None, Thing) # default
    client.register_thing_class('/type/edition', Edition)
    client.register_thing_class('/type/work', Work)
    client.register_thing_class('/type/author', Author)
    client.register_thing_class('/type/user', User)
    client.register_thing_class('/type/list', List)
    client.register_thing_class('/type/library', Library)

def register_types():
    """Register default types for various path patterns used in OL.
    """
    from infogami.utils import types

    types.register_type('^/authors/[^/]*$', '/type/author')
    types.register_type('^/books/[^/]*$', '/type/edition')
    types.register_type('^/works/[^/]*$', '/type/work')
    types.register_type('^/languages/[^/]*$', '/type/language')
    types.register_type('^/libraries/[^/]*$', '/type/library')

    types.register_type('^/usergroup/[^/]*$', '/type/usergroup')
    types.register_type('^/permission/[^/]*$', '/type/permission')

    types.register_type('^/(css|js)/[^/]*$', '/type/rawtext')
