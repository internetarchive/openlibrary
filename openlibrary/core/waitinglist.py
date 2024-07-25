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
from .sendmail import sendmail_with_template
from . import lending


logger = logging.getLogger("openlibrary.waitinglist")

_wl_api = lending.ia_lending_api


def _get_book(identifier):
    if keys := web.ctx.site.things({"type": '/type/edition', "ocaid": identifier}):
        return web.ctx.site.get(keys[0])
    else:
        key = "/books/ia:" + identifier
        return web.ctx.site.get(key)


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


def on_waitinglist_update(identifier):
    """Triggered when a waiting list is updated."""
    waitinglist = []  # Updated waiting list logic here
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


# Any remaining logic related to waiting list would be here
