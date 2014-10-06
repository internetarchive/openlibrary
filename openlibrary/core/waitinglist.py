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
from .sendmail import sendmail_with_template
from . import db
import logging

logger = logging.getLogger("openlibrary.waitinglist")

class WaitingLoan(dict):
    def get_book(self):
        return web.ctx.site.get(self['book_key'])

    def get_user(self):
        return web.ctx.site.get(self['user_key'])

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
        kw.setdefault('order', 'since')
        # as of web.py 0.33, the version used by OL, 
        # db.where doesn't work with no conditions
        if len(kw) > 1: # if has more keys other than "order"
            result = db.where("waitingloan", **kw)
        else:
            result = db.select('waitingloan')
        return [cls(row) for row in result]

    @classmethod
    def new(cls, **kw):
        id = db.insert('waitingloan', **kw)
        result = db.where('waitingloan', id=id)
        return cls(result[0])

    @classmethod
    def find(cls, user_key, book_key):
        """Returns the waitingloan for given book_key and user_key.

        Returns None if there is no such waiting loan.
        """
        result = cls.query(book_key=book_key, user_key=user_key)
        if result:
            return result[0]

    @classmethod
    def prune_expired(cls, book_key=None):
        """Deletes the expired loans from database and returns WaitingLoan objects
        for each deleted row.

        If book_key is specified, it deletes only the expired waiting loans of that book.
        """
        # Anand - Aug 19, 2014
        # Disabled expiring waiting loans as many people are falling out of WL
        # without being able to borrow books.
        return

        where = ""
        if book_key:
            where += " AND book_key=$book_key"
        rows = db.query(
            "DELETE FROM waitingloan" +
            " WHERE expiry IS NOT NULL AND expiry < CURRENT_TIMESTAMP " + where +
            " RETURNING *", vars=locals())
        return [cls(row) for row in rows]
            
    def delete(self):
        """Delete this waiting loan from database.
        """
        db.delete("waitingloan", where="id=$id", vars=self)

    def update(self, **kw):
        db.update("waitingloan", where="id=$id", vars=self, **kw)
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
    """Returns the lost of  records for the users waiting for given book.

    This is admin-only feature. Works only if the current user is an admin.
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
    key = "ebooks" + book_key
    ebook = web.ctx.site.store.get(key) or {}
    size = ebook.get("wl_size", 0)
    return int(size)

def get_waitinglist_for_user(user_key):
    """Returns the list of records for all the books that a user is waiting for.
    """
    # return _query_values(name="user", value=user_key)
    return WaitingLoan.query(user_key=user_key)

def is_user_waiting_for(user_key, book_key):
    """Returns True if the user is waiting for specified book.
    """
    return WaitingLoan.find(user_key, book_key) is not None
    # return get_waiting_loan_object(user_key, book_key) is not None

def get_waiting_loan_object(user_key, book_key):
    return WaitingLoan.find(user_key, book_key)

def get_waitinglist_position(user_key, book_key):
    w = WaitingLoan.find(user_key, book_key)
    if w:
        return w['position']
    else:
        return -1

def join_waitinglist(user_key, book_key):
    """Adds a user to the waiting list of given book.

    It is done by createing a new record in the store.
    """
    book = web.ctx.site.get(book_key)
    if book and book.ocaid:
        WaitingLoan.new(user_key=user_key, book_key=book_key, identifier=book.ocaid)
        update_waitinglist(book_key)

def leave_waitinglist(user_key, book_key):
    """Removes the given user from the waiting list of the given book.
    """
    w = WaitingLoan.find(user_key, book_key)
    if w:
        w.delete()
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
    logger.info("BEGIN updating %r", book_key)
    book = web.ctx.site.get(book_key)
    checkedout = _is_loaned_out(book_key)

    if checkedout:
        loans = book.get_loans()
        # Delete from waiting list if a user has already borrowed this book        
        for loan in loans:
            w = WaitingLoan.find(loan['user'], book_key)
            if w:
                w.delete()

    with db.transaction():
        # delete expired any, if any before we start processing.
        WaitingLoan.prune_expired(book_key=book_key)

        # update the position and wl_size for all holds
        wl = get_waitinglist_for_book(book_key)
        for i, w in enumerate(wl):
            w.update(position=i+1, wl_size=len(wl))

        # Mark the first entry in the waiting-list as available if the book
        # is not checked out.
        if not checkedout and wl and wl[0]['status'] != 'available':
            expiry = datetime.datetime.utcnow() + datetime.timedelta(days=1)
            wl[0].update(status='available', expiry=expiry)

    ebook_key = "ebooks" + book_key
    ebook = web.ctx.site.store.get(ebook_key) or {}

    # for the end user, a book is not available if it is either
    # checked out or someone is waiting.
    not_available = bool(checkedout or wl)

    # update ebook document.
    ebook2 =dict(ebook)
    ebook2.update({
        "_key": ebook_key,
        "type": "ebook",
        "book_key": book_key,
        "borrowed": str(not_available).lower(), # store as string "true" or "false"
        "wl_size": len(wl)
    })
    if ebook != ebook2: # save if modified
        web.ctx.site.store[ebook_key] = dict(ebook2, _rev=None) # force update

    if wl:
        # If some people are waiting and the book is checked out,
        # send email to the person who borrowed the book.
        # 
        # If the book is not checked out, inform the first person 
        # in the waiting list
        if checkedout:
            sendmail_people_waiting(book)        
        else:
            sendmail_book_available(book)
    logger.info("END updating %r", book_key)

def _is_loaned_out(book_key):
    book = web.ctx.site.get(book_key)

    # Anand - Aug 2014
    # When a book is loaned out, there'll be a loan-$ocaid record
    # and get_available_loans() will return empty. 
    # Testing for both of them to make sure we don't give wrong 
    # result even if there is a slight chance for them to differ.
    if book.ocaid:
        loan = web.ctx.site.store.get("loan-" + book.ocaid)
        if loan:
            return True

    # Anand - August 25, 2014
    # Noticed some cases where the book is made available for waitlisted users
    # and also checked out on ACS4. Adding an extra check to avoid that case.
    from openlibrary.plugins.upstream import borrow
    if borrow.is_loaned_out_on_acs4(book.ocaid):
        return True

    # Will this return empty list if archive.org is down?
    return book.get_available_loans() == []

def sendmail_book_available(book):
    """Informs the first person in the waiting list that the book is available.

    Safe to call multiple times. This'll make sure the email is sent only once.
    """
    wl = book.get_waitinglist()
    if wl and wl[0]['status'] == 'available' and not wl[0].get('available_email_sent'):
        record = wl[0]
        user = record.get_user()
        email = user and user.get_email()
        sendmail_with_template("email/waitinglist_book_available", to=email, user=user, book=book)
        record.update(available_email_sent=True)
        logger.info("%s is available, send email to the first person in WL. wl-size=%s", book.key, len(wl))

def sendmail_people_waiting(book):
    """Send mail to the person who borrowed the book when the first person joins the waiting list.

    Safe to call multiple times. This'll make sure the email is sent only once.
    """
    # also supports multiple loans per book
    loans = [loan for loan in book.get_loans() if not loan.get("waiting_email_sent")]
    for loan in loans:
        # don't bother the person if the he has borrowed less than 2 days back
        ndays = 2
        if _get_loan_timestamp_in_days(loan) < ndays:
            continue

        # Only send email reminder for bookreader loans.
        # It seems it is hard to return epub/pdf loans, esp. with bluefire reader and overdrive
        if loan.get("resource_type") != "bookreader":
            return

        # Anand - Oct 2013
        # unfinished PDF/ePub loan?
        # Added temporarily to avoid crashing
        if not loan.get('expiry'):
            continue
        user = web.ctx.site.get(loan["user"])
        email = user and user.get_email()
        sendmail_with_template("email/waitinglist_people_waiting", to=email, 
            user=user, 
            book=book, 
            expiry_days=_get_expiry_in_days(loan))
        loan['waiting_email_sent'] = True
        web.ctx.site.store[loan['_key']] = loan
        logger.info("%s sendmail_people_waiting. wl-size=%s", book.key, book.get_waitinglist_size())

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
    expired = WaitingLoan.prune_expired()
    # Update the checkedout status and position in the WL for each entry
    for r in expired:
        update_waitinglist(r['book_key'])

def update_all_waitinglists():
    rows = db.query("SELECT distinct(book_key) from waitingloan")
    for row in rows:
        try:
            update_waitinglist(row.book_key)
        except Exception:
            logger.error("failed to update waitinglist for %s", row.book_key, exc_info=True)

def update_all_ebook_documents():
    """Updates the status of all ebook documents which are marked as checkedout.

    It is safe to call this function multiple times.
    """
    records = web.ctx.site.store.values(type="ebook", name="borrowed", value="true", limit=-1)
    for r in records:
        try:
            update_waitinglist(r['book_key'])
        except Exception:
            logger.error("failed to update %s", r['book_key'], exc_info=True)

def sync_waitingloans():
    """Syncs the waitingloans from store to db.
    """
    with db.transaction():
        records = web.ctx.site.store.values(type="waiting-loan", limit=-1)
        for r in records:
            w = WaitingLoan.find(r['user'], r['book'])
            if not w:
                WaitingLoan.new(
                    user_key=r['user'],
                    book_key=r['book'],
                    status=r['status'],
                    position=r['position'],
                    wl_size=r['wl_size'],
                    since=r['since'],
                    last_update=r['last-update'],
                    expiry=r.get('expiry'),
                    available_email_sent=r.get('available_email_sent', False))

def verify_sync():
    records = web.ctx.site.store.values(type="waiting-loan", limit=-1)
    for r in records:
        w = WaitingLoan.find(r['user'], r['book'])
        if w is None:
            print "MISSING", r['user'], r['book']
        else:
            def values(d, keys):
                return [d.get(k) for k in keys]
            keys = ['status', 'position', 'wl_size']
            if values(w, ['user_key', 'book_key'] + keys) != values(r, ['user', 'book'] + keys):
                print "MISMATCH", w, r
                print values(w, ['user_key', 'book_key'] + keys)
                print values(r, ['user', 'book'] + keys)
