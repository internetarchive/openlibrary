"""Where the books that need a hand come from.

First Edits is three separable parts: supply (which books are candidates),
ranking (which to show first) and the task page (the context to act). This
module is the supply. Each source returns ``Candidate`` rows; the list pages
turn them into tasks with ``tasks.tasks_for_edition`` and order them with
``ranking``.

Two sources today. The demo set stands in for "popular books with gaps" until
the Solr popularity sort lands in phase 2; the reading log is live.
"""

from dataclasses import dataclass
from typing import Literal

import web

from openlibrary.core import db
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.first_edits import fixtures
from openlibrary.i18n import gettext as _
from openlibrary.utils.isbn import isbn_13_to_isbn_10

Shelf = Literal["want-to-read", "currently-reading", "already-read"]
SHELVES: tuple[Shelf, ...] = ("already-read", "currently-reading", "want-to-read")


@dataclass(frozen=True)
class Candidate:
    edition: object
    readers: int | None = None
    reason: str = ""  # one line on why this book is in the list, shown under the title
    group: int = 0  # coarse order the supply wants kept (shelf rank); ranking sorts within it


def edition_by_isbn(isbn13: str):
    for fld, value in (("isbn_13", isbn13), ("isbn_10", isbn_13_to_isbn_10(isbn13))):
        if value and (keys := web.ctx.site.things({"type": "/type/edition", fld: value, "limit": 1})):
            return web.ctx.site.get(keys[0])
    return None


def demo_candidates() -> list[Candidate]:
    """Resolve the demo set by production key in one batch; fall back to ISBN where the key is absent or another book (dev)."""
    entries = fixtures.load_demo_books()
    by_key = {ed.key: ed for ed in web.ctx.site.get_many([e["key"] for e in entries if e.get("key")])}
    out = []
    for entry in entries:
        ed = by_key.get(entry.get("key"))
        if not ed or ed.get_isbn13() != entry["isbn13"]:
            ed = edition_by_isbn(entry["isbn13"])
        if ed:
            out.append(Candidate(ed, entry.get("readers", 0)))
    return out


def pick_edition(editions: list, logged_key: str | None = None):
    """The one edition of a logged work worth asking about.

    The edition the reader logged wins: they are the person who can answer
    for that printing. Otherwise an edition we hold outside evidence for,
    otherwise any with an ISBN so the link-outs work.
    """
    if logged_key and (hit := next((e for e in editions if e.key == logged_key), None)):
        return hit
    with_evidence = [e for e in editions if e.get_isbn13() and fixtures.load_evidence(e.get_isbn13())]
    if with_evidence:
        return with_evidence[0]
    return next((e for e in editions if e.get_isbn13()), None)


def _shelf_reason(shelf: Shelf, logged: bool) -> str:
    if shelf == "already-read":
        return _("You've read this one.") if logged else _("You've read this; we picked the most common edition.")
    if shelf == "currently-reading":
        return _("You're reading this edition.") if logged else _("You're reading this; we picked the most common edition.")
    return _("On your Want to Read shelf.")


@dataclass(frozen=True)
class LoggedRow:
    work_key: str
    edition_key: str | None
    shelf: Shelf


def logged_rows(username: str) -> list[LoggedRow]:
    """Every book on the reader's three shelves, straight from the reading-log table, newest first within each shelf.

    The Solr-backed reading log pages at 100 and carries no ISBNs, so it can't
    tell us which of 200 books we have evidence for. One query here can.
    """
    names: dict[str, Shelf] = {"Already Read": "already-read", "Currently Reading": "currently-reading", "Want to Read": "want-to-read"}
    ids = {Bookshelves.PRESET_BOOKSHELVES[name]: shelf for name, shelf in names.items()}
    rows = db.get_db().query(
        "SELECT work_id, edition_id, bookshelf_id FROM bookshelves_books WHERE username=$username AND bookshelf_id IN $ids ORDER BY created DESC",
        vars={"username": username, "ids": list(ids)},
    )
    return [LoggedRow(f"/works/OL{r.work_id}W", f"/books/OL{r.edition_id}M" if r.edition_id else None, ids[r.bookshelf_id]) for r in rows]


def split_logged(rows: list[LoggedRow], isbn_of: dict[str, str | None], evidence: frozenset[str]) -> tuple[list[LoggedRow], list[LoggedRow]]:
    """Rows whose logged edition we hold evidence for, and rows that would need the work's editions scanned.

    ``isbn_of`` maps a logged edition key to its ISBN-13 (None when the record
    has none or wasn't found). Pure, so the cheap/expensive split is testable.
    """
    ready, scan = [], []
    for row in rows:
        if row.edition_key and (isbn_of.get(row.edition_key) in evidence):
            ready.append(row)
        else:
            scan.append(row)
    return ready, scan


def shelf_candidates(user, scan_limit: int = 40) -> list[Candidate]:
    """The reader's logged works, each reduced to one edition. Read shelves first: that is where they hold the book.

    Cheap path: the editions the reader logged, fetched in one batch and kept
    when we hold evidence for their ISBN. Expensive path, capped at
    ``scan_limit`` most recent: works logged without an edition, whose editions
    have to be loaded to find one with evidence.
    """
    rows = logged_rows(user.get_username())
    evidence = fixtures.evidence_isbns()
    editions = {e.key: e for e in web.ctx.site.get_many([r.edition_key for r in rows if r.edition_key]) if e}
    isbn_of = {key: ed.get_isbn13() for key, ed in editions.items()}
    ready, scan = split_logged(rows, isbn_of, evidence)

    picked: dict[str, tuple[object, Shelf, bool]] = {}
    for row in ready:
        picked.setdefault(row.work_key, (editions[row.edition_key], row.shelf, True))
    for row in scan[:scan_limit]:
        if row.work_key in picked or not (work := web.ctx.site.get(row.work_key)):
            continue
        if pick := pick_edition(work.get_sorted_editions(), None):
            picked[row.work_key] = (pick, row.shelf, False)

    rank = {shelf: i for i, shelf in enumerate(SHELVES)}
    return [Candidate(ed, None, _shelf_reason(shelf, logged), rank[shelf]) for ed, shelf, logged in picked.values()]
