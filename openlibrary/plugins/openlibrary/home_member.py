"""What the home page shows a signed-in reader above everything else: the book they have in hand, whatever else
is in progress, and the books on their Want to Read list they could start today.

The home page itself is cached and the same for everyone, so this is fetched after load by
HomeMemberPartial (partials.py) and rendered with home/member.html.jinja.
"""

import logging
from datetime import UTC, datetime

import web

from openlibrary.core import cache, lending
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.i18n import gettext as _
from openlibrary.i18n import ungettext
from openlibrary.utils import dateutil
from openlibrary.utils.request_context import get_request_lang, req_context, site

logger = logging.getLogger("openlibrary.home")

# Want to Read books checked for a free copy, and how many of those are shown (two rows of covers).
WANT_CHECKED = 40
WANT_SHOWN = 14
# How many books are listed under the one in hand.
AGENDA_SIDE = 2
# How long a reader's rendered section is kept. Shelf changes, borrows and returns drop it sooner.
MEMBER_CACHE_SECS = 5 * dateutil.MINUTE_SECS
# A loan this close to its due date is marked.
URGENT_DAYS = 2


# A display name longer than this is left out of the greeting.
GREETING_NAME_MAX = 30


def _brief(title: str, author: str, url: str, cover_url: str) -> dict:
    """What a card shows. `thumb_url` is the small rendition, for the 24px covers on the one-line rows."""
    return {"title": title or _("Untitled"), "author": author, "url": url, "cover_url": cover_url, "thumb_url": cover_url.replace("-M.jpg", "-S.jpg")}


def brief_from_doc(doc: dict) -> dict:
    """A Solr work doc as a card."""
    from openlibrary.plugins.openlibrary.partials import _resolve_carousel_card_cover_url

    return _brief(doc.get("title", ""), ", ".join((doc.get("author_name") or [])[:2]), doc.get("key", ""), _resolve_carousel_card_cover_url(doc) or "")


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
    return _brief(book.title, authors, book.url(), cover)


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

    The first is the large card: the book in hand (the loan due soonest, else the newest Currently Reading
    book with a free copy, else the newest), since that's what most visits are for. After it comes whatever
    has a clock on it: ready holds, then the other loans.
    """

    def card(book: dict, kind: str, status: str, tone: str, label: str, form: dict | None = None) -> dict:
        return {
            "kind": kind,
            "title": book["title"],
            "author": book["author"],
            "url": book["url"],
            "cover_url": book["cover_url"],
            "thumb_url": book["thumb_url"],
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
    # A Currently Reading book says nothing about itself and has no button of ours: the template gives it a
    # Read or Borrow button when a copy is free (`cta`), and the control that moves it off the shelf (`shelf`).
    reading_cards = [
        card(book, "reading", "", "plain", "") | {"action": None} | {key: book.get(key, "") for key in ("cta", "shelf", "work_key")} for book in reading
    ]
    if not loan_cards:
        # The large card should have something to press: the newest book with a free copy, else the newest.
        lead = next((book for book in reading_cards if book["cta"]), None)
        if lead:
            reading_cards = [lead] + [book for book in reading_cards if book is not lead]
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


def reading_now(readlog) -> list[dict]:
    """The newest of the Currently Reading shelf, as many as the card can hold. Each book carries a Read or Borrow button when a copy is
    free right now, and the shelf control that moves it to Already Read or off the list."""
    from markupsafe import Markup

    from openlibrary.plugins.openlibrary.partials import _render_carousel_card_loan_status
    from openlibrary.plugins.upstream.mybooks import shelf_button_for

    # A few more than the card holds: a shelved work that search doesn't know comes back without a title.
    docs = [doc for doc in readlog.get_works("currently-reading", limit=AGENDA_SIDE + 3).docs if doc.get("title")][: AGENDA_SIDE + 1]
    lending.add_availability(docs)
    books = []
    for doc in docs:
        free = (doc.get("availability") or {}).get("status") in ("open", "borrow_available")
        # Without `editions` the button is for the work, whose availability names the free copy.
        work = web.storage({k: v for k, v in doc.items() if k != "editions"})

        # `ol-carousel` is the layout that gets the small button.
        cta = _render_carousel_card_loan_status(work, work_key=work.get("key"), key="home-reading", layout="ol-carousel") if free else ""

        books.append(
            brief_from_doc(doc)
            | {
                "work_key": doc.get("key", ""),
                "cta": cta,
                # A caret button that opens the shelf menu.
                "shelf": Markup(shelf_button_for(doc, variant="menu", size="small", async_load=True)),
            }
        )
    return books


def greeting_name(user) -> str:
    """The name to greet the reader by, or "" when all we have is a username or something too long for a heading."""
    name = (getattr(user, "displayname", None) or "").strip()
    username = (getattr(user, "key", None) or "").split("/")[-1]
    return name if name and name != username and len(name) <= GREETING_NAME_MAX else ""


def build_member(user) -> dict:
    """Everything of the reader's own the home page shows. Each part fails on its own, so a lending outage
    costs the loans and not the section."""
    from openlibrary.plugins.upstream.mybooks import ReadingLog

    failed = []

    def attempt(what, fn, fallback):
        try:
            return fn()
        except Exception:
            logger.error("home: could not load %s", what, exc_info=True)
            failed.append(what)
            return fallback

    readlog = ReadingLog(user)
    loans = attempt("loans", lambda: get_loans(user.key), [])
    holds = attempt("holds", lambda: get_holds(user), [])
    reading = attempt("currently reading", lambda: reading_now(readlog), [])
    # A borrowed book is usually on Currently Reading too; it is shown once, as the loan.
    on_loan = {loan["title"] for loan in loans}
    reading = [brief for brief in reading if brief["title"] not in on_loan]

    want = attempt("want to read", lambda: want_available(readlog), [])

    return {
        "name": greeting_name(user),
        "agenda": build_agenda(loans, holds, reading),
        "side": AGENDA_SIDE,
        "want": [brief_from_doc(doc) for doc in want],
        "complete": not failed,
    }


# The rendered section is kept per reader. One memcache entry holds a rendering per language (and per
# print-disabled setting, which changes what counts as borrowable), each tagged with the reading log's
# version so a shelf change makes it stale. A borrow or return deletes the entry.


def _cache_key(username: str) -> str:
    return cache.build_memcache_key("home.member", username)


def _cache_variant(username: str) -> str:
    return ":".join([Bookshelves.reading_log_version(username), get_request_lang() or "", "pd" if req_context.get().print_disabled else ""])


def get_cached_html(username: str) -> str | None:
    return (cache.get_memcache().get(_cache_key(username)) or {}).get(_cache_variant(username))


def cache_html(username: str, html: str) -> None:
    mc = cache.get_memcache()
    variant = _cache_variant(username)
    version = variant.split(":", 1)[0]
    current = {k: v for k, v in (mc.get(_cache_key(username)) or {}).items() if k.startswith(version)}
    mc.set(_cache_key(username), current | {variant: html}, expires=MEMBER_CACHE_SECS)


def invalidate_cache(username: str) -> None:
    cache.get_memcache().delete(_cache_key(username))
