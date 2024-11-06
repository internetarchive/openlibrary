"""
Controllers for /borrow pages.

These endpoints are largely deprecated, and only maintained for
backwards compatibility.
"""

import web

import datetime
import json

import eventer

from infogami.utils import delegate
from infogami.utils.view import render_template  # noqa: F401 used for its side effects

from openlibrary.core import statsdb


class borrow(delegate.page):
    path = "/borrow"

    def GET(self):
        raise web.seeother('/subjects/in_library#ebooks=true')


class borrow_json(delegate.page):
    path = "/borrow"
    encoding = "json"

    def GET(self):
        raise web.seeother('/subjects/in_library.json' + web.ctx.query)


class read(delegate.page):
    path = "/read"

    def GET(self):
        web.seeother('/subjects/accessible_book#ebooks=true')


class read_json(delegate.page):
    path = "/read"
    encoding = "json"

    def GET(self):
        web.seeother('/subjects/accessible_book.json' + web.ctx.query)


def on_loan_created_statsdb(loan):
    """Adds the loan info to the stats database."""
    key = _get_loan_key(loan)
    t_start = datetime.datetime.utcfromtimestamp(loan['loaned_at'])
    d = {
        "book": loan['book'],
        "identifier": loan['ocaid'],
        "resource_type": loan['resource_type'],
        "t_start": t_start.isoformat(),
        "status": "active",
    }
    d['library'] = "/libraries/internet_archive"
    d['geoip_country'] = None  # we removed geoip
    statsdb.add_entry(key, d)


def on_loan_completed_statsdb(loan):
    """Marks the loan as completed in the stats database."""
    key = _get_loan_key(loan)
    t_start = datetime.datetime.utcfromtimestamp(loan['loaned_at'])
    t_end = datetime.datetime.utcfromtimestamp(loan['returned_at'])
    d = {
        "book": loan['book'],
        "identifier": loan['ocaid'],
        "resource_type": loan['resource_type'],
        "t_start": t_start.isoformat(),
        "t_end": t_end.isoformat(),
        "status": "completed",
    }
    if old := statsdb.get_entry(key):
        olddata = json.loads(old.json)
        d = dict(olddata, **d)
    statsdb.update_entry(key, d)


def _get_loan_key(loan):
    # The loan key is now changed from uuid to fixed key.
    # Using _key as key for loan stats will result in overwriting previous loans.
    # Using the unique uuid to create the loan key and falling back to _key
    # when uuid is not available.
    return "loans/" + loan.get("uuid") or loan["_key"]


def setup():
    eventer.bind("loan-created", on_loan_created_statsdb)
    eventer.bind("loan-completed", on_loan_completed_statsdb)
