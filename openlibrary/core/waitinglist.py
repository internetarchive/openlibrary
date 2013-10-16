"""Implementation of waiting-list feature for OL loans.

Each waiting instance is represented as a document in the store as follows:

    {
        "_key": "waiting-loan-OL123M-anand",
        "type": "waiting-loan",
        "user": "/people/anand",
        "book": "/books/OL123M",
        "status": "waiting",
        "since": "2013-09-16T06:09:16.577942",
        "last-update": "2013-10-01T06:09:16.577942"
    }
"""
import datetime
import web
from . import helpers as h

class WaitingLoan(dict):
    def get_book(self):
        return web.ctx.site.get(self['book'])

    def get_position(self):
        return self['position']

    def get_waitinglist_size(self):
        return self['wl_size']

    def get_waiting_in_days(self):
        since = h.parse_datetime(self['since'])
        delta = datetime.datetime.utcnow() - since
        # Adding 1 to round off the the extra seconds in the delta
        return delta.days + 1

    def get_expiry_in_hours(self):
        if "expiry" in self:
            delta = datetime.datetime.utcnow() - h.parse_datetime(self['expiry'])
            delta_seconds = delta.days * 24 * 3600 + delta.seconds
            delta_hours = delta_seconds / 3600
            return max(0, delta_hours)
        return 0

def _query_values(name, value):
    docs = web.ctx.site.store.values(type="waiting-loan", name=name, value=value, limit=1000)
    return [WaitingLoan(doc) for doc in docs]

def _query_keys(name, value):
    return web.ctx.site.store.keys(type="waiting-loan", name=name, value=value, limit=1000)

def get_waitinglist_for_book(book_key):
    """Returns the lost of  records for the users waiting for given book.

    This is admin-only feature. Works only if the current user is an admin.
    """
    wl = _query_values(name="book", value=book_key)
    # sort the waiting list by timestamp
    return sorted(wl, key=lambda doc: doc['since'])

def get_waitinglist_size(book_key):
    """Returns size of the waiting list for given book.
    """
    key = "ebooks" + book_key
    ebook = web.ctx.site.store.get(key) or {}
    size = ebook.get("wl_size", 0)
    return int(size)

def get_waitinglist_for_user(user_key):
    """Returns the list of records for all the books that a user is waiting for.
    """
    return _query_values(name="user", value=user_key)

def is_user_waiting_for(user_key, book_key):
    """Returns True if the user is waiting for specified book.
    """
    return get_waiting_loan_object(user_key, book_key) is not None

def get_waiting_loan_object(user_key, book_key):
    ukey = user_key.split("/")[-1]
    bkey = book_key.split("/")[-1]
    key = "waiting-loan-%s-%s" % (ukey, bkey)
    doc = web.ctx.site.store.get(key)
    if doc and doc['status'] != 'expired':
        return WaitingLoan(doc)

def get_waitinglist_position(user_key, book_key):
    ukey = user_key.split("/")[-1]
    bkey = book_key.split("/")[-1]
    key = "waiting-loan-%s-%s" % (ukey, bkey)

    wl = get_waitinglist_for_book(book_key)
    keys = [doc['_key'] for doc in wl]
    try:
        # Adding one to start the position from 1 instead of 0
        return keys.index(key) + 1
    except ValueError:
        return -1

def join_waitinglist(user_key, book_key):
    """Adds a user to the waiting list of given book.

    It is done by createing a new record in the store.
    """
    ukey = user_key.split("/")[-1]
    bkey = book_key.split("/")[-1]
    key = "waiting-loan-%s-%s" % (ukey, bkey)
    timestamp = datetime.datetime.utcnow().isoformat()

    d = {
        "_key": key,
        "type": "waiting-loan",
        "user": user_key,
        "book": book_key,
        "status": "waiting",
        "since": timestamp,
        "last-update": timestamp,
    }
    web.ctx.site.store[key] = d
    update_waitinglist(book_key)

def leave_waitinglist(user_key, book_key):
    """Removes the given user from the waiting list of the given book.
    """
    ukey = user_key.split("/")[-1]
    bkey = book_key.split("/")[-1]
    key = "waiting-loan-%s-%s" % (ukey, bkey)
    web.ctx.site.store.delete(key)
    update_waitinglist(book_key)

def update_waitinglist(book_key):
    """Updates the status of the waiting list.

    It does the following things:

    * updates the position of each person the waiting list (do we need this?)
    * marks the first one in the waiting-list as active if the book is available to borrow
    * updates the waiting list size in the ebook document (this is used by solr to index wl size)
    * If the person who borrowed the book is in the waiting list, removed it (should never happen)

    This function should be called on the following events:
    * When a book is checked out or returned
    * When a person joins or leaves the waiting list
    """
    wl = get_waitinglist_for_book(book_key)
    checkedout = _is_loaned_out(book_key)

    ebook_key = "ebooks" + book_key
    ebook = web.ctx.site.store.get(ebook_key) or {}

    documents = {}
    def save_later(doc):
        """Remembers to save on commit."""
        documents[doc['_key']] = doc

    def commit():
        """Saves all the documents """
        web.ctx.site.store.update(documents)

    if checkedout:
        book = web.ctx.site.get(book_key)
        loans = book.get_loans()
        
        loaned_users = [loan['user'] for loan in loans]
        for doc in wl[:]:
            # Delete from waiting list if a user has already borrowed this book
            if doc['user'] in loaned_users:
                doc['_delete'] = True
                save_later(doc)
                wl.remove(doc)

    for i, doc in enumerate(wl):
        doc['position'] = i + 1
        doc['wl_size'] = len(wl)
        save_later(doc)

    # Mark the first entry in the waiting-list as available if the book
    # is not checked out.
    if not checkedout and wl:
        wl[0]['status'] = 'available'
        save_later(wl[0])

    # for the end user, a book is not available if it is either
    # checked out or someone is waiting.
    not_available = bool(checkedout or wl)

    # update ebook document.
    ebook.update({
        "_key": ebook_key,
        "type": "ebook",
        "book_key": book_key,
        "borrowed": str(not_available).lower(), # store as string "true" or "false"
        "wl_size": len(wl)
    })
    save_later(ebook)
    commit()

def _is_loaned_out(book_key):
    from openlibrary.plugins.upstream import borrow
    book = web.ctx.site.get(book_key)
    return borrow.get_edition_loans(book) != []
