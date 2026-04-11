import json
import logging
from collections import defaultdict

import web

from infogami.utils import delegate
from infogami.utils.view import require_login
from openlibrary import accounts
from openlibrary.core import db
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.bookshelves_events import BookshelfEvent, BookshelvesEvents
from openlibrary.core.models import Edition, Ratings
from openlibrary.plugins.upstream.checkins import make_date_string
from openlibrary.utils import extract_numeric_id_from_olid

logger = logging.getLogger("openlibrary.dataimporter")

_DEFAULT_SHELVES = {
    'to_read': 1,
    'currently_reading': 2,
    'read': 3,
}

_IGNORED_SHELVES = {'did_not_finish'}


def _normalize_shelf_name(name: str) -> str:
    """Standardizes shelf names for consistent lookup and creation."""
    return name.strip().lower().translate(str.maketrans(' -', '__'))


def _get_edition_from_isbn(isbn, isbn_cache):
    """Retrieves an Edition via ISBN/ASIN, using a memory cache to avoid redundant lookups."""
    if not isbn:
        return None

    isbn_val, asin = Edition.get_isbn_or_asin(isbn)
    if not Edition.is_valid_identifier(isbn_val, asin):
        return None

    forms = Edition.get_identifier_forms(isbn_val, asin)

    for f in forms:
        if f in isbn_cache:
            return isbn_cache[f]

    edition = Edition.from_isbn(isbn)
    if edition:
        for f in forms:
            isbn_cache[f] = edition

    return edition


def _prepare_context(user, username, oldb):
    """Initializes the shared memory state and queues for batch database inserts."""
    books_already_in_default_bookshelves = oldb.query(
        "SELECT work_id, bookshelf_id FROM bookshelves_books WHERE username=$username",
        vars={'username': username},
    )

    return {
        "books_in_bookshelves": {  # To check if book already in bookshelf
            (str(e.work_id), int(e.bookshelf_id))
            for e in books_already_in_default_bookshelves
        },
        "lists_map": {  # list-name: list object
            _normalize_shelf_name(lst.name): lst
            for lst in user.get_lists(limit=None)
            if getattr(lst, 'name', None)
        },
        "isbn_cache": {},
        "works_in_list_cache": {},
        "lists_to_save": set(),  # Tracks dirty lists
        "pending_seeds": defaultdict(
            list
        ),  # Queues new books to be added to custom lists
        "pending_bookshelf_inserts": [],  # Queues raw rows for the bookshelves_books table
        "pending_dateread_events": [],  # Queues raw rows for the bookshelves_events (dates read) table
    }


def _process_this_books_shelves(
    book, user, username, work_id, work_key, edition_id, ctx
):
    """Maps Goodreads shelves to Open Library shelves/lists, and handles list/book insertions."""
    shelves = {_normalize_shelf_name(s) for s in book.get('shelves', [])}

    for norm_shelf in shelves:
        # Ignore the did_not_finish shelf
        if norm_shelf in _IGNORED_SHELVES:
            continue

        # 1. Handle creation of completely new custom lists
        if norm_shelf not in _DEFAULT_SHELVES and norm_shelf not in ctx['lists_map']:
            new_list = user.new_list(
                norm_shelf.replace('_', ' ').title(),
                "Imported from Goodreads",
                seeds=[],
            )
            ctx['lists_map'][norm_shelf] = new_list
            ctx['lists_to_save'].add(norm_shelf)

        # 2. Handle default Open Library shelves (Read, Currently Reading, Want to Read)
        if norm_shelf in _DEFAULT_SHELVES:
            shelf_id = _DEFAULT_SHELVES[norm_shelf]

            if (work_id, shelf_id) not in ctx['books_in_bookshelves']:
                ctx['pending_bookshelf_inserts'].append(
                    {
                        'username': username,
                        'bookshelf_id': shelf_id,
                        'work_id': work_id,
                        'edition_id': edition_id,
                    }
                )
                ctx['books_in_bookshelves'].add((work_id, shelf_id))

        # 3. Handle adding books to custom lists
        elif norm_shelf in ctx['lists_map']:
            target_list = ctx['lists_map'][norm_shelf]

            # Lazy-load existing seeds for this list into memory on first access
            if norm_shelf not in ctx['works_in_list_cache']:
                ctx['works_in_list_cache'][norm_shelf] = {
                    s.key if hasattr(s, 'key') else s.get('key')
                    for s in (getattr(target_list, 'seeds', []) or [])
                }

            if work_key in ctx['works_in_list_cache'][norm_shelf]:
                continue

            ctx['pending_seeds'][norm_shelf].append({"key": work_key})
            ctx['lists_to_save'].add(norm_shelf)
            ctx['works_in_list_cache'][norm_shelf].add(work_key)


def _process_this_books_rating(book, username, work_id, edition_id, ctx):
    """
    Processes the 1-5 star user rating for a book.
    Updates the context to prevent `_process_this_books_shelves` from writing
    duplicate "Already Read" entries, as Ratings.add() enforces this inherently.
    """
    raw_rating = book.get('rating')

    if not raw_rating or raw_rating == "0":
        return

    try:
        rating_val = int(raw_rating)
        if 1 <= rating_val <= 5:
            # Prevent double-insert conflict: Ratings.add() forces the book onto the 'Read' shelf.
            # We add it to the context here so the shelf processor skips queueing it a second time.
            ctx["books_in_bookshelves"].add((int(work_id), _DEFAULT_SHELVES['read']))

            Ratings.add(
                username=username,
                work_id=work_id,
                rating=rating_val,
                edition_id=edition_id,
            )
    except (ValueError, TypeError):
        logger.warning(
            f"Invalid rating value '{raw_rating}' for row {book.get('row_id', '')}"
        )


def _process_this_book_date_read(book, username, work_id, edition_id, ctx):
    """Parses completion dates and queues the event insertion."""
    raw_date_read = book.get('date_read')

    if not raw_date_read:
        return

    try:
        parts = [
            int(p)
            for p in str(raw_date_read).replace("/", "-").strip().split("-")
            if p.strip()
        ]
        if not parts:
            return

        year = parts[0]
        month = parts[1] if len(parts) > 1 else None
        day = parts[2] if len(parts) > 2 else None

        ctx["pending_dateread_events"].append(
            {
                'username': username,
                'work_id': work_id,
                'edition_id': edition_id or BookshelvesEvents.NULL_EDITION_ID,
                'event_date': make_date_string(year, month, day),
                'event_type': BookshelfEvent.FINISH,
            }
        )
    except (ValueError, TypeError) as e:
        logger.warning(
            f"Failed to parse date_read '{raw_date_read}' for row {book.get('row_id', '')}: {e}"
        )


def _process_book(book, user, username, ctx):
    """Master processor for resolving a book's identity and delegating its data processing."""
    if not isinstance(book, dict):
        return {
            "row_id": None,
            "status": "error",
            "reason": "Invalid book format payload. Expected a dictionary object.",
        }

    row_id = book.get('row_id', '')

    isbn = str(book.get('isbn', '')).replace('="', '').replace('"', '').strip()
    isbn13 = str(book.get('isbn13', '')).replace('="', '').replace('"', '').strip()

    if not isbn and not isbn13:
        return {"row_id": row_id, "status": "error", "reason": "No valid ISBN provided"}

    try:
        edition = _get_edition_from_isbn(
            isbn13, ctx["isbn_cache"]
        ) or _get_edition_from_isbn(isbn, ctx["isbn_cache"])
        if not edition or not getattr(edition, 'works', None):
            return {
                "row_id": row_id,
                "status": "error",
                "reason": "Book not found in Open Library",
            }

        work_key = (
            edition.works[0]['key']
            if isinstance(edition.works[0], dict)
            else getattr(edition.works[0], 'key', None)
        )
        if not work_key:
            return {
                "row_id": row_id,
                "status": "error",
                "reason": "Missing Work mapping",
            }

        work_id = extract_numeric_id_from_olid(work_key)
        edition_id = extract_numeric_id_from_olid(edition.key)

        # IMPORTANT:
        # Ratings must be processed first so it can register the "Already Read" side-effect
        # in the context dictionary before the shelves processor runs.
        _process_this_books_rating(book, username, work_id, edition_id, ctx)
        _process_this_books_shelves(
            book, user, username, work_id, work_key, edition_id, ctx
        )
        _process_this_book_date_read(book, username, work_id, edition_id, ctx)

        return {"row_id": row_id, "status": "success"}

    except Exception as e:
        logger.error(f"Error processing book with Row ID {row_id}: {e}", exc_info=True)
        return {"row_id": row_id, "status": "error", "reason": "Internal server error"}


def _commit_changes(oldb, ctx):
    """Executes all bulk inserts and saves custom list modifications."""
    if ctx["pending_bookshelf_inserts"]:
        oldb.multiple_insert(Bookshelves.TABLENAME, ctx["pending_bookshelf_inserts"])

    if ctx["pending_dateread_events"]:
        oldb.multiple_insert(
            BookshelvesEvents.TABLENAME, ctx["pending_dateread_events"]
        )

    for list_name in ctx["lists_to_save"]:
        target_list = ctx["lists_map"][list_name]

        if list_name in ctx["pending_seeds"]:
            target_list.seeds = (
                list(getattr(target_list, 'seeds', []) or [])
                + ctx["pending_seeds"][list_name]
            )

        target_list._save(comment="Added books via Goodreads import")


class process_imports(delegate.page):
    path = "/account/import/process/goodreads"

    @require_login
    def POST(self):
        raw = web.data()

        if not raw:
            return delegate.RawText(
                json.dumps({"error": "missing_body"}),
                status="400 Bad Request",
                content_type="application/json",
            )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return delegate.RawText(
                json.dumps({"error": "invalid_json"}),
                status="400 Bad Request",
                content_type="application/json",
            )

        books = data.get("books")
        if not isinstance(books, list):
            return delegate.RawText(
                json.dumps({"error": "books_must_be_list"}),
                status="400 Bad Request",
                content_type="application/json",
            )

        try:
            user = accounts.get_current_user()
            username = user.get_username()
            oldb = db.get_db()

            ctx = _prepare_context(user, username, oldb)

            results = [_process_book(book, user, username, ctx) for book in books]

            _commit_changes(oldb, ctx)

            return delegate.RawText(
                json.dumps({"results": results}), content_type="application/json"
            )

        except Exception as e:
            logger.error(f"Error in process_imports: {e}", exc_info=True)
            raise web.HTTPError(
                "500 Internal Server Error",
                headers={"Content-Type": "application/json"},
            )


def setup():
    pass
