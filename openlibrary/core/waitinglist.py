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
import logging
from infogami.infobase.client import ClientException

logger = logging.getLogger("openlibrary.waitinglist")

class WaitingLoan(dict):
    def get_book(self):
        return web.ctx.site.get(self['book'])

    def get_user(self):
        return web.ctx.site.get(self['user'])

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
    logger.info("BEGIN updating %r", book_key)
    wl = get_waitinglist_for_book(book_key)
    checkedout = _is_loaned_out(book_key)

    ebook_key = "ebooks" + book_key
    ebook = web.ctx.site.store.get(ebook_key) or {}

    documents = {}
    def save_later(doc):
        """Remembers to save on commit."""
        documents[doc['_key']] = doc

    def update_doc(doc, **kwargs):
        dirty = False
        for name, value in kwargs.items():
            if doc.get(name) != value:
                doc[name] = value
                dirty = True
        if dirty:
            save_later(doc)

    def commit():
        """Saves all the documents """
        try:
            web.ctx.site.store.update(documents)
        except ClientException, e:
            logger.error("Failed to save documents.", exc_info=True)
            logger.error("Error data: %r", e.get_data())

    if checkedout:
        book = web.ctx.site.get(book_key)
        loans = book.get_loans()
        
        loaned_users = [loan['user'] for loan in loans]
        for doc in wl[:]:
            # Delete from waiting list if a user has already borrowed this book
            if doc['user'] in loaned_users:
                update_doc(doc, _delete=True)
                wl.remove(doc)

    for i, doc in enumerate(wl):
        update_doc(doc, position=i+1, wl_size=len(wl))

    # Mark the first entry in the waiting-list as available if the book
    # is not checked out.
    if not checkedout and wl:
        # one day
        expiry = datetime.datetime.utcnow() + datetime.timedelta(1)
        update_doc(wl[0], status='available', expiry=expiry.isoformat())

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

    book = web.ctx.site.get(book_key)
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
    from openlibrary.plugins.upstream import borrow
    book = web.ctx.site.get(book_key)
    return borrow.get_edition_loans(book) != []

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
        record['available_email_sent'] = True
        web.ctx.site.store[record['_key']] = record

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
    records = web.ctx.site.store.values(type="waiting-loan", name="status", value="available", limit=-1)
    now = datetime.datetime.utcnow().isoformat()
    expired = [r for r in records if 'expiry' in r and r['expiry'] < now]
    for r in expired:
        logger.info("Deleting waiting loan for %r", r['book'])
        # should mark record as expired instead of deleting
        r['_delete'] = True
    web.ctx.site.store.update(dict((r['_key'], r) for r in expired))

    # Update the checkedout status and position in the WL for each entry
    for r in expired:
        update_waitinglist(r['book'])

def update_all_ebook_documents():
    """Updates the status of all ebook documents which are marked as checkedout.

    It is safe to call this function multiple times.
    """
    records = web.ctx.site.store.values(type="ebook", name="borrowed", value="true", limit=-1)
    for r in records:
        update_waitinglist(r['book_key'])