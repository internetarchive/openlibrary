"""What the home page shows a signed-in reader above everything else: the books they have out on loan or a hold
ready to borrow, then the ones they borrowed lately, and the books on their Currently Reading and Want to Read
shelves they could open today.

The home page itself is cached and the same for everyone, so this is fetched after load by
HomeMemberPartial (partials.py) and rendered with home/member.html.jinja, in two halves.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from urllib.parse import urlencode

from openlibrary.accounts.model import parse_s3_cookie
from openlibrary.core import cache, helpers, lending
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.i18n import gettext as _
from openlibrary.i18n import ungettext
from openlibrary.utils import dateutil
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.request_context import get_request_lang, req_context, site

logger = logging.getLogger("openlibrary.home")

# Books of each shelf checked for a free copy, and how many of those are sent: one row of covers, clipped to the width.
READING_CHECKED = 6
WANT_CHECKED = 30
ROW_SHOWN = 14
# How many loans and ready holds the card lists. Slots they leave empty go to the books borrowed lately.
LOANS_SHOWN = 2
# Past loans read to fill those slots: more than there are slots, as some are books the reader has out now.
PAST_LOANS_CHECKED = 6
# How long the loan history and its availability may take together before the card goes on without them.
HISTORY_BUDGET_SECS = 2
# Editions of a work checked for a free copy, after the one the reader shelved.
COPIES_CHECKED = 5
# How many of a work's ebook editions search hands over to choose those from, the reader's language first.
COPIES_FETCHED = 12
EDITIONS_TIMEOUT_SECS = 2
# How long the section waits on availability, over its checks together, before it goes on without.
AVAILABILITY_BUDGET_SECS = 3
# How long a reader's rendered section is kept. Shelf changes, borrows and returns drop it sooner.
MEMBER_CACHE_SECS = 5 * dateutil.MINUTE_SECS
# A loan this close to its due date is marked.
URGENT_DAYS = 2


# A display name longer than this is left out of the greeting.
GREETING_NAME_MAX = 30


def _brief(title: str, author: str, url: str, cover_url: str, work_key: str = "") -> dict:
    """What a card shows. `thumb_url` is the small rendition, for the 24px covers on the one-line rows.
    `work_key` is the same for every edition of a book, so one book is shown once."""
    return {
        "title": title or _("Untitled"),
        "author": author,
        "url": url,
        "cover_url": cover_url,
        "thumb_url": cover_url.replace("-M.jpg", "-S.jpg"),
        "work_key": work_key or url,
    }


def brief_from_doc(doc: dict) -> dict:
    """A Solr work doc as a card."""
    from openlibrary.plugins.openlibrary.partials import _resolve_carousel_card_cover_url

    # The cover of the edition on offer when it has one of its own (see AvailabilityBudget.add), else the work's.
    cover_of = {"cover_i": cover} if (cover := (doc.get("offered_edition") or {}).get("cover_i")) else doc
    return _brief(doc.get("title", ""), ", ".join((doc.get("author_name") or [])[:2]), doc.get("key", ""), _resolve_carousel_card_cover_url(cover_of) or "")


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
    works = getattr(book, "works", None)
    return _brief(book.title, authors, book.url(), cover, works[0].key if works else book.key)


def due_label(days_left: int) -> str:
    if days_left <= 0:
        return _("Due back today")
    if days_left == 1:
        return _("Due back tomorrow")
    return ungettext("Due back in %(count)d day", "Due back in %(count)d days", days_left, count=days_left)


def borrowed_label(updatedate: str) -> str:
    """When a past loan was last borrowed, from the loan history's `updatedate` (UTC, "2026-11-20 14:03:11")."""
    try:
        then = datetime.fromisoformat(updatedate)
    except TypeError, ValueError:
        return _("Borrowed before")
    now = datetime.now(UTC).replace(tzinfo=None)
    return _("Borrowed %(when)s", when=helpers.datestr(then.replace(tzinfo=None), now=now))


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
    today = datetime.now(UTC).date()
    for loan in lending.get_cached_loans_of_user(user_key):
        if not (book_key := loan.get("book")) or not (book := _resolve(site.get().get(book_key))):
            continue
        days_left = None
        if expiry := loan.get("expiry"):
            try:
                # Calendar days, not whole 24-hour periods, so "tomorrow" is the next date (in UTC, as IA keeps it).
                days_left = max(0, (datetime.fromisoformat(expiry).date() - today).days)
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


async def _loan_history_async(s3_keys: dict) -> tuple[list[dict], dict]:
    """The reader's latest loan records from IA, newest first, and the availability of each item."""
    response = await lending.s3_loan_api_async(s3_keys=s3_keys, action="user_borrow_history", limit=PAST_LOANS_CHECKED, offset=0, newest=True)
    items = [item for item in (response.json().get("history") or {}).get("items") or [] if item.get("identifier")]
    return items, await lending.get_availability_async("identifier", [item["identifier"] for item in items])


def get_past_loans(s3_cookie: str | None) -> list[dict]:
    """The books this reader borrowed lately, most recent first, with what they can do about each now.
    A one-hour loan is over before the reader is back, so this is how they find the book again."""
    if not (s3_keys := parse_s3_cookie(s3_cookie)):
        return []
    try:
        items, availability = async_bridge.run(asyncio.wait_for(_loan_history_async(s3_keys), HISTORY_BUDGET_SECS))
    except TimeoutError:
        logger.warning("home: the loan history took longer than the %ss the card allows", HISTORY_BUDGET_SECS)
        return []
    editions = lending.editions_for_availability(availability)
    past = []
    # Books only on archive.org have no page here to send the reader to.
    for item in items:
        if book := editions.get(item["identifier"]):
            past.append(
                brief_from_book(book)
                | {"borrowed": borrowed_label(item.get("updatedate") or ""), "availability": book.get("availability") or {}, "borrow_url": book.url("/borrow")}
            )
    return past


def past_loan_action(book: dict) -> tuple[str, dict | None, bool]:
    """The button on a past loan: its label, the borrow form it posts (None to link to the book), and whether it opens the book."""
    status = book["availability"].get("status")
    if status == "open":
        return _("Read"), None, True
    if is_free(book["availability"]):
        return _("Borrow again"), {"action": book["borrow_url"], "value": "borrow"}, True
    if status == "borrow_unavailable":
        return _("Join waitlist"), {"action": book["borrow_url"], "value": "join-waitinglist"}, False
    # A book that can't be lent at all says why on its page.
    return _("View book"), None, False


def build_loans(loans: list[dict], holds: list[dict], past: list[dict] | None = None) -> list[dict]:
    """Loans, soonest due first, then holds ready to borrow, then books borrowed lately that aren't either,
    each with a status line and one button. A hold still in line has nothing to do yet and is left to the
    loans page."""

    def card(book: dict, kind: str, status: str, tone: str, label: str, form: dict | None, access: bool) -> dict:
        return {
            "kind": kind,
            "title": book["title"],
            "author": book["author"],
            "url": book["url"],
            "cover_url": book["cover_url"],
            "thumb_url": book["thumb_url"],
            "status": status,
            "tone": tone,
            # Borrowing and reading take the primary fill, as they do across the site.
            "action": {"label": label, "href": book["url"], "form": form, "access": access},
        }

    loan_cards = [
        card(
            loan,
            "loan",
            loan["due"] or _("On loan"),
            "urgent" if loan["urgent"] else "plain",
            _("Continue reading"),
            {"action": f"/borrow/ia/{loan['ocaid']}", "value": "read"} if loan["can_read_here"] else None,
            True,
        )
        for loan in loans
    ]
    # A ready hold's status is how long it is kept: the heading already says it is ready.
    ready = [
        card(hold, "ready", hold["note"], "ready", _("Borrow now"), {"action": hold["borrow_url"], "value": "borrow"}, True) for hold in holds if hold["ready"]
    ]
    taken = {book.get("work_key") for book in loans + holds}
    past_cards = []
    for book in past or []:
        if book["work_key"] in taken:
            continue
        taken.add(book["work_key"])
        past_cards.append(card(book, "past", book["borrowed"], "plain", *past_loan_action(book)))
    return loan_cards + ready + past_cards


def availability_known(docs: list) -> bool:
    """False when the availability service answered for none of the books: an outage, not a shelf with nothing free."""
    statuses = [(doc.get("availability") or {}).get("status") for doc in docs if lending.get_ocaid(doc)]
    return not statuses or any(status and status != "error" for status in statuses)


FREE = ("open", "borrow_available")


def is_free(availability: dict | None) -> bool:
    """Whether this reader can open the copy now. A print-disabled reader can also read any copy in the
    print-disabled collection, lent out or not, as the Read button (LoanStatus) offers them."""
    availability = availability or {}
    return availability.get("status") in FREE or bool(availability.get("is_printdisabled") and req_context.get().print_disabled)


def _logged_edition(doc) -> dict | None:
    """The edition the reader shelved, when they shelved one. Solr hands it as a list, or as a dict holding `docs`."""
    editions = doc.get("editions") or []
    if isinstance(editions, dict):
        editions = editions.get("docs") or []
    return editions[0] if isinstance(editions, list) and editions else None


def readable_editions(docs: list) -> dict[str, list[dict]] | None:
    """For each work, the editions with an ebook that this reader could read: in the language they browse in,
    or with no language recorded, the first kind first. A work whose ebooks are all known to be in other
    languages gets none. None when search can't say, and the work's own lending copy is used as before."""
    from openlibrary.plugins.upstream.utils import convert_iso_to_marc
    from openlibrary.plugins.worksearch.schemes.works import get_fulltext_min
    from openlibrary.plugins.worksearch.search import get_solr

    try:
        lang = convert_iso_to_marc(get_request_lang() or "en") or "eng"
        params = [
            ("q", "{!terms f=key}" + ",".join(doc["key"] for doc in docs)),
            ("fl", "key,copies:[subquery]"),
            ("rows", len(docs)),
            ("copies.q", f"+({{!terms f=_root_ v=$row.key}}) language:{lang}^40 ebook_access:public^10 ebook_access:borrowable^8"),
            ("copies.fq", "type:edition"),
            ("copies.fq", f"ebook_access:[{get_fulltext_min()} TO *]"),
            ("copies.rows", COPIES_FETCHED),
            ("copies.fl", "key,ia,language,ebook_access,cover_i"),
            ("wt", "json"),
        ]
        answer = async_bridge.run(get_solr().raw_request("select", urlencode(params), _timeout=EDITIONS_TIMEOUT_SECS)).json()
        if answer.get("responseHeader", {}).get("partialResults"):
            # Search ran out of time: what it sent is not every edition, and would leave books off wrongly.
            raise TimeoutError("partial results")
        found = answer["response"]["docs"]
    except Exception:
        logger.warning("home: could not read editions by language", exc_info=True)
        return None

    def readable(edition: dict) -> bool:
        return bool(edition.get("ia")) and (not edition.get("language") or lang in edition["language"])

    # Narrowed here and not in the query: a filter on "no language recorded" is built over every edition there is.
    return {work["key"]: [e for e in (work.get("copies") or {}).get("docs") or [] if readable(e)][:COPIES_CHECKED] for work in found}


class AvailabilityBudget:
    """The time the section's availability checks may take between them. The lending timeout is far longer,
    and the reader is looking at a skeleton meanwhile."""

    def __init__(self, secs: float = AVAILABILITY_BUDGET_SECS):
        self.left = secs

    def add(self, docs: list) -> bool:
        """Reads availability onto `docs`. False when time ran out or the service answered for none of them.

        Each work gets the copy to offer, the first one free of: the edition the reader shelved, since it's
        the version they chose, then the editions they could read (readable_editions). A translation they
        didn't choose is never offered. One request covers every copy."""
        logged = {doc["key"]: edition for doc in docs if (edition := _logged_edition(doc)) and lending.get_ocaid(edition)}
        if not any(lending.get_ocaid(doc) for doc in docs) and not logged:
            return True
        if self.left <= 0:
            return False
        readable = readable_editions(docs)
        copies = {doc["key"]: [logged[doc["key"]]] if doc["key"] in logged else [] for doc in docs}
        for doc in docs:
            copies[doc["key"]] += [doc] if readable is None else readable.get(doc["key"], [])
        checked = [copy for of_work in copies.values() for copy in of_work]
        started = time.monotonic()
        try:
            async_bridge.run(asyncio.wait_for(lending.add_availability_async(checked), self.left))
        except TimeoutError:
            logger.warning("home: availability took longer than the %ss the section allows", AVAILABILITY_BUDGET_SECS)
            return False
        finally:
            self.left -= time.monotonic() - started
        for doc in docs:
            of_work = [copy for copy in copies[doc["key"]] if copy.get("availability")]
            pick = next((copy for copy in of_work if is_free(copy["availability"])), of_work[0] if of_work else None)
            doc["availability"] = pick["availability"] | {"identifier": lending.get_ocaid(pick)} if pick else {}
            # Only the shelved edition lends its cover: the reader knows the book by it.
            if pick is logged.get(doc["key"]) and pick and is_free(pick["availability"]):
                doc["offered_edition"] = pick
        return availability_known(checked)


def shelves_available(readlog, budget: AvailabilityBudget) -> tuple[list, bool]:
    """Currently Reading then Want to Read, narrowed twice: to works Solr says can be borrowed at all, then to
    the ones with a copy free at this moment. A work on both shelves is shown once, as Currently Reading. When
    availability can't be read the second narrowing is skipped, and False is returned with the books so the
    row doesn't promise "now". Each doc gets `shelf`, the one it came from."""
    from openlibrary.plugins.worksearch.schemes.works import get_fulltext_min

    fq = [f"ebook_access:[{get_fulltext_min()} TO *]"]
    docs, seen = [], set()
    for shelf, limit in (("currently-reading", READING_CHECKED), ("want-to-read", WANT_CHECKED)):
        for doc in readlog.get_works(shelf, limit=limit, fq=fq).docs:
            if doc.get("title") and doc["key"] not in seen:
                seen.add(doc["key"])
                doc["shelf"] = "reading" if shelf == "currently-reading" else "want"
                docs.append(doc)
    if not budget.add(docs):
        return docs[:ROW_SHOWN], False
    return [doc for doc in docs if is_free(doc.get("availability"))][:ROW_SHOWN], True


def want_brief(doc: dict, checked: bool) -> dict:
    """A card for a shelved book. A book found free links to the copy that was checked, since the work page
    picks its edition by other rules and can land on one that isn't."""
    brief = brief_from_doc(doc) | {"shelf": doc.get("shelf", "want")}
    if checked and brief["url"] and (ocaid := (doc.get("availability") or {}).get("identifier") or lending.get_ocaid(doc)):
        brief["url"] += f"?edition=ia:{ocaid}"
    return brief


def greeting_name(user) -> str:
    """The name to greet the reader by, or "" when all we have is a username or something too long for a heading."""
    name = (getattr(user, "displayname", None) or "").strip()
    username = (getattr(user, "key", None) or "").split("/")[-1]
    return name if name and name != username and len(name) <= GREETING_NAME_MAX else ""


# The section's two halves, each fetched and kept on its own so the quicker one doesn't wait for the other.
PARTS = ("loans", "shelves")


def build_part(user, part: str, s3_cookie: str | None = None) -> dict:
    """One half of what the home page shows of the reader's own: `loans` is their loans and ready holds, topped
    up with the books they borrowed lately (the loan history is read with their `s3_cookie`), `shelves` their
    Currently Reading and Want to Read books with a copy free. Each piece fails on its own, so a lending outage
    costs the loans and not the holds. Without availability the row is the shelves as they stand. A half missing
    its loans, holds or availability is built again on the next view; one missing only the loan history is kept,
    so a slow or failing history isn't asked for on every view."""
    from openlibrary.plugins.upstream.mybooks import ReadingLog

    failed = []

    def attempt(what, fn, fallback, required=True):
        try:
            return fn()
        except Exception:
            logger.error("home: could not load %s", what, exc_info=True)
            if required:
                failed.append(what)
            return fallback

    member: dict = {"name": greeting_name(user), "part": part}
    known = True
    if part == "shelves":
        books, known = attempt("shelves", lambda: shelves_available(ReadingLog(user), AvailabilityBudget()), ([], True))
        # `shelves_checked` is false when the row is the shelves as they stand, not checked for a free copy.
        member |= {"shelves": [want_brief(doc, known) for doc in books], "shelves_checked": known}
    else:
        loans = attempt("loans", lambda: get_loans(user.key), [])
        holds = attempt("holds", lambda: get_holds(user), [])
        past = []
        if len(loans) + sum(hold["ready"] for hold in holds) < LOANS_SHOWN:
            past = attempt("loan history", lambda: get_past_loans(s3_cookie), [], required=False)
        member |= {"loans": build_loans(loans, holds, past)[:LOANS_SHOWN]}
    # A half built without availability is shown, and built again on the next view.
    return member | {"complete": not failed and known}


# Each rendered half is kept per reader. One memcache entry holds a rendering per language (and per
# print-disabled setting, which changes what counts as borrowable), each tagged with the reading log's
# version so a shelf change makes it stale. A borrow or return deletes both halves' entries.


def _cache_key(username: str, part: str) -> str:
    return cache.build_memcache_key("home.member", part, username)


def cache_variant(username: str) -> str:
    """Read once before a half is built and stored under, so a shelf change during the build leaves it stale."""
    return ":".join([Bookshelves.reading_log_version(username), get_request_lang() or "", "pd" if req_context.get().print_disabled else ""])


def get_cached_html(username: str, part: str, variant: str) -> str | None:
    return (cache.get_memcache().get(_cache_key(username, part)) or {}).get(variant)


def cache_html(username: str, part: str, html: str, variant: str) -> None:
    mc = cache.get_memcache()
    version = variant.split(":", 1)[0]
    current = {k: v for k, v in (mc.get(_cache_key(username, part)) or {}).items() if k.startswith(version)}
    mc.set(_cache_key(username, part), current | {variant: html}, expires=MEMBER_CACHE_SECS)


def invalidate_cache(username: str) -> None:
    for part in PARTS:
        cache.get_memcache().delete(_cache_key(username, part))
