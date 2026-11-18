"""What the home page shows a signed-in reader above everything else: the book they have in hand, whatever else
is in progress, and the books on their Want to Read list they could start today.

The home page itself is cached and the same for everyone, so this is fetched after load by
HomeMemberPartial (partials.py) and rendered with home/member.html.jinja.
"""

import logging
from datetime import UTC, datetime

from openlibrary.core import lending
from openlibrary.i18n import gettext as _
from openlibrary.i18n import ungettext
from openlibrary.utils.request_context import site

logger = logging.getLogger("openlibrary.home")

# Want to Read books checked for a free copy, and how many of those are shown (two rows of covers).
WANT_CHECKED = 40
WANT_SHOWN = 14
# How many books are listed under the one in hand.
AGENDA_SIDE = 3
# A loan this close to its due date is marked.
URGENT_DAYS = 2


def brief_from_doc(doc: dict) -> dict:
    """A Solr work doc, cut down to what a card shows."""
    from openlibrary.plugins.openlibrary.partials import _resolve_carousel_card_cover_url

    return {
        "title": doc.get("title") or _("Untitled"),
        "author": ", ".join((doc.get("author_name") or [])[:2]),
        "url": doc.get("key", ""),
        "cover_url": _resolve_carousel_card_cover_url(doc) or "",
    }


def brief_from_book(book) -> dict:
    """An edition (or work) Thing as the same card."""
    try:
        authors = ", ".join(a.name for a in book.get_authors()[:2] if a and a.name)
    except Exception:  # noqa: BLE001  an edition with a broken author link still gets a card
        authors = ""
    try:
        cover = book.get_cover_url("M") or ""
    except Exception:  # noqa: BLE001
        cover = ""
    return {"title": book.title or _("Untitled"), "author": authors, "url": book.url(), "cover_url": cover}


def due_label(days_left: int) -> str:
    if days_left <= 0:
        return _("Due back today")
    if days_left == 1:
        return _("Due back tomorrow")
    return _("Due back in %(count)d days", count=days_left)


def ready_label(hours_left: float) -> str:
    """How long a ready hold is kept before it goes to the next reader."""
    if hours_left <= 0:
        return _("Borrow it soon, or it goes to the next reader.")
    if hours_left < 24:
        hours = max(1, round(hours_left))
        return ungettext("Held for you for %(count)d more hour.", "Held for you for %(count)d more hours.", hours, count=hours)
    days = round(hours_left / 24)
    return ungettext("Held for you for %(count)d more day.", "Held for you for %(count)d more days.", days, count=days)


def waiting_label(position: int, size: int) -> str:
    if position <= 1:
        return _("You're next in line")
    return _("You're number %(position)d of %(size)d in line", position=position, size=size)


def _resolve(book):
    """Follow a redirect chain a few hops, as My Books does for loans on merged editions."""
    for _hop in range(5):
        if book and getattr(getattr(book, "type", None), "key", None) == "/type/redirect":
            book = site.get().get(book.location)
        else:
            break
    return book


def get_loans(user_key: str) -> list[dict]:
    """Active loans, soonest due first."""
    loans = []
    now = datetime.now(UTC).replace(tzinfo=None)
    for loan in lending.get_cached_loans_of_user(user_key):
        if not (book_key := loan.get("book")) or not (book := _resolve(site.get().get(book_key))):
            continue
        days_left = None
        if expiry := loan.get("expiry"):
            try:
                days_left = max(0, (datetime.fromisoformat(expiry).replace(tzinfo=None) - now).days)
            except ValueError:
                days_left = None
        loans.append(
            brief_from_book(book)
            | {
                "ocaid": loan.get("ocaid"),
                "can_read_here": loan.get("resource_type") == "bookreader" and bool(loan.get("ocaid")),
                "days_left": days_left,
                "due": due_label(days_left) if days_left is not None else "",
                "urgent": days_left is not None and days_left <= URGENT_DAYS,
            }
        )
    return sorted(loans, key=lambda loan: loan["days_left"] if loan["days_left"] is not None else 99)


def get_holds(user) -> list[dict]:
    """The waiting list, ready holds first."""
    holds = []
    for hold in user.get_waitinglist():
        if not (book := _resolve(hold.get_book())):
            continue
        ready = hold.get("status") == "available"
        holds.append(
            brief_from_book(book)
            | {
                "ready": ready,
                "borrow_url": book.url("/borrow"),
                "note": ready_label(hold.get_expiry_in_hours() or 0) if ready else waiting_label(hold.get_position(), hold.get_waitinglist_size()),
            }
        )
    return sorted(holds, key=lambda hold: not hold["ready"])


def build_agenda(loans: list[dict], holds: list[dict], reading: list[dict]) -> list[dict]:
    """Loans, holds and Currently Reading books as one list of cards, each with a status line and one action.

    The first is the large card: the book in hand (the loan due soonest, else what they're reading), since
    that's what most visits are for. After it comes whatever has a clock on it: ready holds, then the other loans.
    """

    def card(book: dict, kind: str, status: str, tone: str, label: str, form: dict | None = None) -> dict:
        return {
            "kind": kind,
            "title": book["title"],
            "author": book["author"],
            "url": book["url"],
            "cover_url": book["cover_url"],
            "status": status,
            "tone": tone,
            "action": {"label": label, "href": book["url"], "form": form},
        }

    loan_cards = [
        card(
            loan,
            "loan",
            loan["due"] or _("On loan"),
            "urgent" if loan["urgent"] else "plain",
            _("Continue reading"),
            {"action": f"/borrow/ia/{loan['ocaid']}", "value": "read"} if loan["can_read_here"] else None,
        )
        for loan in loans
    ]
    ready = [
        card(hold, "ready", _("Your hold is ready"), "ready", _("Borrow now"), {"action": hold["borrow_url"], "value": "borrow"}) | {"note": hold["note"]}
        for hold in holds
        if hold["ready"]
    ]
    waiting = [card(hold, "waiting", hold["note"], "plain", _("View")) for hold in holds if not hold["ready"]]
    reading_cards = [card(book, "reading", _("Currently reading"), "plain", _("Open the book")) for book in reading]
    in_hand = loan_cards[:1] or reading_cards[:1]
    rest = ready + loan_cards[1:] + (reading_cards if loan_cards else reading_cards[1:]) + waiting
    return in_hand + rest


def want_available(readlog) -> list:
    """Want to Read, narrowed twice: to works Solr says can be borrowed at all, then to the ones with a copy
    free at this moment. Empty when availability can't be read: the row promises "now"."""
    from openlibrary.plugins.worksearch.schemes.works import get_fulltext_min

    works = readlog.get_works("want-to-read", limit=WANT_CHECKED, fq=[f"ebook_access:[{get_fulltext_min()} TO *]"])
    docs = [doc for doc in works.docs if doc.get("title")]
    lending.add_availability(docs)
    return [doc for doc in docs if (doc.get("availability") or {}).get("status") in ("open", "borrow_available")][:WANT_SHOWN]


def build_member(user) -> dict:
    """Everything of the reader's own the home page shows. Each part fails on its own, so a lending outage
    costs the loans and not the section."""
    from openlibrary.plugins.upstream.mybooks import ReadingLog

    def attempt(what, fn, fallback):
        try:
            return fn()
        except Exception:
            logger.error("home: could not load %s", what, exc_info=True)
            return fallback

    readlog = ReadingLog(user)
    loans = attempt("loans", lambda: get_loans(user.key), [])
    holds = attempt("holds", lambda: get_holds(user), [])
    reading = attempt("currently reading", lambda: readlog.get_works("currently-reading", limit=6).docs, [])
    # A borrowed book is usually on Currently Reading too; it is shown once, as the loan.
    on_loan = {loan["title"] for loan in loans}
    reading = [brief for brief in map(brief_from_doc, reading) if brief["title"] not in on_loan]

    want = attempt("want to read", lambda: want_available(readlog), [])

    return {
        "agenda": build_agenda(loans, holds, reading),
        "side": AGENDA_SIDE,
        "want": [brief_from_doc(doc) for doc in want],
    }
