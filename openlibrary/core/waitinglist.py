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
import logging
import urllib, urllib2
import json
import web
from infogami import config
from . import helpers as h
from .sendmail import sendmail_with_template
from . import db
from . import lending

logger = logging.getLogger("openlibrary.waitinglist")

_wl_api = lending.ia_lending_api


def userkey2userid(user_key):
    username = user_key.split("/")[-1]
    return "ol:" + username

def userid2userkey(userid):
    if userid and userid.startswith("ol:"):
        return "/people/" + userid[len("ol:"):]

def _get_book(identifier):
    keys = web.ctx.site.things(dict(type='/type/edition', ocaid=identifier))
    if keys:
        return web.ctx.site.get(keys[0])
    else:
        key = "/books/ia:" + identifier
        return web.ctx.site.get(key)

class WaitingLoan(dict):
    def get_book(self):
        return _get_book(self['identifier'])

    def get_user_key(self):
        return self.get("user_key") or userid2userkey(self.get("userid"))

    def get_user(self):
        user_key = self.get_user_key()
        return user_key and web.ctx.site.get(user_key)

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
            delta = h.parse_datetime(self['expiry']) - datetime.datetime.utcnow()
            delta_seconds = delta.days * 24 * 3600 + delta.seconds
            delta_hours = delta_seconds / 3600
            return max(0, delta_hours)
        return 0

    def is_expired(self):
        return self['status'] == 'available' and self['expiry'] < datetime.datetime.utcnow().isoformat()

    def dict(self):
        """Converts this object into JSON-able dict.

        Converts all datetime objects into strings.
        """
        def process_value(v):
            if isinstance(v, datetime.datetime):
                v = v.isoformat()
            return v
        return dict((k, process_value(v)) for k, v in self.items())

    @classmethod
    def query(cls, **kw):
        rows = _wl_api.query(**kw) or []
        return [cls(row) for row in rows]

    @classmethod
    def new(cls, **kw):
        _wl_api.join_waitinglist(kw['identifier'], userkey2userid(kw['user_key']))
        return cls.find(kw['user_key'], kw['identifier'])

    @classmethod
    def find(cls, user_key, identifier):
        """Returns the waitingloan for given book_key and user_key.

        Returns None if there is no such waiting loan.
        """
        result = cls.query(userid=userkey2userid(user_key), identifier=identifier)
        if result:
            return result[0]

    def delete(self):
        """Delete this waiting loan from database.
        """
        _wl_api.leave_waitinglist(self['identifier'], self['userid'])
        pass

    def update(self, **kw):
        _wl_api.update_waitinglist(identifier=self['identifier'], userid=self['userid'], **kw)
        dict.update(self, kw)

class Stats:
    def get_popular_books(self, limit=10):
        rows = db.query(
            "select book_key, count(*) as count" +
            " from waitingloan" +
            " group by 1" +
            " order by 2 desc" + 
            " limit $limit", vars=locals()).list()
        docs = web.ctx.site.get_many([row.book_key for row in rows])
        docs_dict = dict((doc.key, doc) for doc in docs)
        for row in rows:
            row.book = docs_dict.get(row.book_key)
        return rows

    def get_counts_by_status(self):
        rows = db.query("SELECT status, count(*) as count FROM waitingloan group by 1 order by 2")
        return rows.list()

    def get_available_waiting_loans(self, offset=0, limit=10):
        rows = db.query(
            "SELECT * FROM waitingloan" +
            " WHERE status='available'" +
            " ORDER BY expiry desc " +
            " OFFSET $offset" +
            " LIMIT $limit",
            vars=locals())
        return [WaitingLoan(row) for row in rows]

def get_waitinglist_for_book(book_key):
    """Returns the list of records for the users waiting for the given book.

    This is an admin-only feature. It works only if the current user is an admin.
    """
    book = web.ctx.site.get(book_key)
    if book and book.ocaid:
        return WaitingLoan.query(identifier=book.ocaid)
    else:
        return []
    # wl = _query_values(name="book", value=book_key)
    # # sort the waiting list by timestamp
    # return sorted(wl, key=lambda doc: doc['since'])

def get_waitinglist_size(book_key):
    """Returns size of the waiting list for given book.
    """
    return len(get_waitinglist_for_book(book_key))

def get_waitinglist_for_user(user_key):
    """Returns the list of records for all the books that a user is waiting for.
    """
    return WaitingLoan.query(userid=userkey2userid(user_key))

def is_user_waiting_for(user_key, book_key):
    """Returns True if the user is waiting for specified book.
    """
    book = web.ctx.site.get(book_key)
    if book and book.ocaid:
        return WaitingLoan.find(user_key, book.ocaid) is not None

def get_waiting_loan_object(user_key, book_key):
    book = web.ctx.site.get(book_key)
    if book and book.ocaid:
        return WaitingLoan.find(user_key, book.ocaid)

def get_waitinglist_position(user_key, book_key):
    book = web.ctx.site.get(book_key)
    if book and book.ocaid:
        w = WaitingLoan.find(user_key, book.ocaid)
        if w:
            return w['position']
    return -1

def join_waitinglist(user_key, book_key):
    """Adds a user to the waiting list of given book.

    It is done by creating a new record in the store.
    """
    book = web.ctx.site.get(book_key)
    if book and book.ocaid:
        WaitingLoan.new(user_key=user_key, identifier=book.ocaid)
        update_waitinglist(book.ocaid)

def leave_waitinglist(user_key, book_key):
    """Removes the given user from the waiting list of the given book.
    """
    book = web.ctx.site.get(book_key)
    if book and book.ocaid:
        w = WaitingLoan.find(user_key, book.ocaid)
        if w:
            w.delete()
            update_waitinglist(book.ocaid)

def update_waitinglist(identifier):
    """Updates the status of the waiting list.

    It does the following things:

    * marks the first one in the waiting-list as active if the book is available to borrow
    * updates the waiting list size in the ebook document (this is used by solr to index wl size)
    * If the person who borrowed the book is in the waiting list, removed it (should never happen)

    This function should be called on the following events:
    * When a book is checked out or returned
    * When a person joins or leaves the waiting list
    """
    _wl_api.request("loan.sync", identifier=identifier)
    return on_waitinglist_update(identifier)


def on_waitinglist_update(identifier):
    """Triggered when a waiting list is updated.
    """
    waitinglist = WaitingLoan.query(identifier=identifier)
    if waitinglist:
        book = _get_book(identifier)
        checkedout = lending.is_loaned_out(identifier)
        # If the book is not checked out, inform the first person 
        # in the waiting list
        if not checkedout:
             sendmail_book_available(book)


def sendmail_book_available(book):
    """Informs the first person in the waiting list that the book is available.

    Safe to call multiple times. This'll make sure the email is sent only once.
    """
    wl = book.get_waitinglist()
    if wl and wl[0]['status'] == 'available' and not wl[0].get('available_email_sent'):
        record = wl[0]
        user = record.get_user()
        if not user:
            return
        email = user.get_email()
        sendmail_with_template("email/waitinglist_book_available", to=email, user=user, book=book)
        record.update(available_email_sent=True)
        logger.info("%s is available, send email to the first person in WL. wl-size=%s", book.key, len(wl))

def _get_expiry_in_days(loan):
    if loan.get("expiry"):
        delta = h.parse_datetime(loan['expiry']) - datetime.datetime.utcnow()
        # +1 to count the partial day
        return delta.days + 1

def _get_loan_timestamp_in_days(loan):
    t = datetime.datetime.fromtimestamp(loan['loaned_at'])
    delta = datetime.datetime.utcnow() - t
    return delta.days
