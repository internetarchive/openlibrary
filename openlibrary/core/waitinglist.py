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

import web

from openlibrary.accounts.model import OpenLibraryAccount

from . import helpers as h
from . import lending
from .sendmail import sendmail_with_template

logger = logging.getLogger("openlibrary.waitinglist")

_wl_api = lending.ia_lending_api


def _get_book(identifier):
    if keys := web.ctx.site.things({"type": '/type/edition', "ocaid": identifier}):
        return web.ctx.site.get(keys[0])
    else:
        key = "/books/ia:" + identifier
        return web.ctx.site.get(key)


class WaitingLoan(dict):
    def get_book(self):
        return _get_book(self['identifier'])

    def get_user_key(self):
        if user_key := self.get("user_key"):
            return user_key

        userid = self.get("userid")
        username = ""
        if userid.startswith('@'):
            account = OpenLibraryAccount.get(link=userid)
            username = account.username
        elif userid.startswith('ol:'):
            username = userid[len("ol:") :]
        return f"/people/{username}"

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
        return (
            self['status'] == 'available'
            and self['expiry'] < datetime.datetime.utcnow().isoformat()
        )

    def dict(self):
        """Converts this object into JSON-able dict.

        Converts all datetime objects into strings.
        """

        def process_value(v):
            if isinstance(v, datetime.datetime):
                v = v.isoformat()
            return v

        return {k: process_value(v) for k, v in self.items()}

    @classmethod
    def query(cls, **kw):
        # kw.setdefault('order', 'since')
        # # as of web.py 0.33, the version used by OL,
        # # db.where doesn't work with no conditions
        # if len(kw) > 1: # if has more keys other than "order"
        #     result = db.where("waitingloan", **kw)
        # else:
        #     result = db.select('waitingloan')
        # return [cls(row) for row in result]
        rows = _wl_api.query(**kw) or []
        return [cls(row) for row in rows]

    @classmethod
    def new(cls, **kw):
        user_key = kw['user_key']
        itemname = kw.get('itemname', '')
        if not itemname:
            account = OpenLibraryAccount.get(key=user_key)
            itemname = account.itemname
        _wl_api.join_waitinglist(kw['identifier'], itemname)
        return cls.find(user_key, kw['identifier'], itemname=itemname)

    @classmethod
    def find(cls, user_key, identifier, itemname=None):
        """Returns the waitingloan for given book_key and user_key.

        Returns None if there is no such waiting loan.
        """
        if not itemname:
            account = OpenLibraryAccount.get(key=user_key)
            itemname = account.itemname
        result = cls.query(userid=itemname, identifier=identifier)
        if result:
            return result[0]

    @classmethod
    def prune_expired(cls, identifier=None):
        """Deletes the expired loans from database and returns WaitingLoan objects
        for each deleted row.

        If book_key is specified, it deletes only the expired waiting loans of that book.
        """
        return

    def delete(self):
        """Delete this waiting loan from database."""
        # db.delete("waitingloan", where="id=$id", vars=self)
        _wl_api.leave_waitinglist(self['identifier'], self['userid'])
        pass

    def update(self, **kw):
        # db.update("waitingloan", where="id=$id", vars=self, **kw)
        _wl_api.update_waitinglist(
            identifier=self['identifier'], userid=self['userid'], **kw
        )
        dict.update(self, kw)


def get_waitinglist_for_book(book_key):
    """Returns the list of records for the users waiting for the given book.

    This is an admin-only feature. It works only if the current user is an admin.
    """
    book = web.ctx.site.get(book_key)
    if book and book.ocaid:
        return WaitingLoan.query(identifier=book.ocaid)
    else:
        return []


def get_waitinglist_size(book_key):
    """Returns size of the waiting list for given book."""
    return len(get_waitinglist_for_book(book_key))


def get_waitinglist_for_user(user_key):
    """Returns the list of records for all the books that a user is waiting for."""
    waitlist = []
    account = OpenLibraryAccount.get(key=user_key)
    if account.itemname:
        waitlist.extend(WaitingLoan.query(userid=account.itemname))
    waitlist.extend(WaitingLoan.query(userid=lending.userkey2userid(user_key)))
    return waitlist


def is_user_waiting_for(user_key, book_key):
    """Returns True if the user is waiting for specified book."""
    book = web.ctx.site.get(book_key)
    if book and book.ocaid:
        return WaitingLoan.find(user_key, book.ocaid) is not None


def join_waitinglist(user_key, book_key, itemname=None):
    """Adds a user to the waiting list of given book.

    It is done by creating a new record in the store.
    """
    book = web.ctx.site.get(book_key)
    if book and book.ocaid:
        WaitingLoan.new(user_key=user_key, identifier=book.ocaid, itemname=itemname)


def leave_waitinglist(user_key, book_key, itemname=None):
    """Removes the given user from the waiting list of the given book."""
    book = web.ctx.site.get(book_key)
    if book and book.ocaid:
        w = WaitingLoan.find(user_key, book.ocaid, itemname=itemname)
        if w:
            w.delete()


def on_waitinglist_update(identifier):
    """Triggered when a waiting list is updated."""
    waitinglist = WaitingLoan.query(identifier=identifier)
    if waitinglist:
        book = _get_book(identifier)
        checkedout = lending.is_loaned_out(identifier)
        # If some people are waiting and the book is checked out,
        # send email to the person who borrowed the book.
        #
        # If the book is not checked out, inform the first person
        # in the waiting list
        if not checkedout:
            sendmail_book_available(book)


def update_ebook(ebook_key, **data):
    ebook = web.ctx.site.store.get(ebook_key) or {}
    # update ebook document.
    ebook2 = dict(ebook, _key=ebook_key, type="ebook")
    ebook2.update(data)
    if ebook != ebook2:  # save if modified
        web.ctx.site.store[ebook_key] = dict(ebook2, _rev=None)  # force update


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
        sendmail_with_template(
            "email/waitinglist_book_available",
            to=email,
            user=user,
            book=book,
            waitinglist_record=record,
        )
        record.update(available_email_sent=True)
        logger.info(
            "%s is available, send email to the first person in WL. wl-size=%s",
            book.key,
            len(wl),
        )


def _get_expiry_in_days(loan):
    if loan.get("expiry"):
        delta = h.parse_datetime(loan['expiry']) - datetime.datetime.utcnow()
        # +1 to count the partial day
        return delta.days + 1


def _get_loan_timestamp_in_days(loan):
    t = datetime.datetime.fromtimestamp(loan['loaned_at'])
    delta = datetime.datetime.utcnow() - t
    return delta.days


def prune_expired_waitingloans():
    """Removes all the waiting loans that are expired.

    A waiting loan expires if the person fails to borrow a book with in
    24 hours after his waiting loan becomes "available".
    """
    return


def update_all_waitinglists():
    rows = WaitingLoan.query(limit=10000)
    identifiers = {row['identifier'] for row in rows}
    for identifier in identifiers:
        try:
            _wl_api.request("loan.sync", identifier=identifier)
        except Exception:
            logger.error(
                "failed to update waitinglist for %s", identifier, exc_info=True
            )


def update_all_ebooks():
    rows = WaitingLoan.query(limit=10000)
    identifiers = {row['identifier'] for row in rows}

    loan_keys = web.ctx.site.store.keys(type='/type/loan', limit=-1)

    for k in loan_keys:
        id = k[len("loan-") :]
        # would have already been updated
        if id in identifiers:
            continue
        logger.info("updating ebooks/" + id)
        update_ebook('ebooks/' + id, borrowed='true', wl_size=0)
