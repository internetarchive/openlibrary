"""An initiative: a fixed list of editions that Tasks works through, and the fields it asks about.

The list is picked once and frozen in the store, so progress means gaps filled, not a pool that drifts as books get fixed.
Nothing builds it by hand: the first request after a deploy starts the pick on a background thread, as ``pool`` does.
Several initiatives run at once; ``/tasks`` opens on ``headline()`` and the others are a click away.

What an initiative is (its name, fields, dates, whether it is hidden) lives in the store too, in a small doc apart from
the list, so it changes without a deploy. ``BUILTIN`` holds the ones defined here; a store doc with the same slug overrides
the keys it names, and a doc with a new slug is a new initiative.
"""

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from infogami.infobase.client import ClientException
from infogami.utils.delegate import create_site
from openlibrary.contribute import pool, tasks
from openlibrary.core import cache
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.helpers import commify, format_date
from openlibrary.core.tags import GENRES, LITERARY_FORMS
from openlibrary.i18n import gettext as _
from openlibrary.i18n import ungettext
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.utils.dateutil import DAY_SECS, MINUTE_SECS
from openlibrary.utils.request_context import site as request_site

logger = logging.getLogger("openlibrary.contribute.initiatives")

# How many people must say "I couldn't find it" before a gap leaves the list. Many books really have no LCCN or OCLC
# number, but nearly every book has a cover, page count, publisher and language, so a miss there is weaker evidence.
NOT_FOUND_PEOPLE = {
    "lccn": 2,
    "oclc_numbers": 2,
    "number_of_pages": 3,
    "publishers": 3,
    "covers": 3,
    "languages": 4,
    # "Not sure": a judgment rather than a lookup, so a few people unsure is a sign the call really is contested.
    LITERARY_FORMS: 3,
    GENRES: 3,
}
NOT_FOUND_TYPE = "contribute-notfound"

# Picking scans Solr for the whole list, so it gets the same room as the old Tasks query.
PICK_TIMEOUT_SECONDS = 120
# How long the open gaps are shared before a background rebuild re-reads every edition on the list.
OPEN_TTL = 10 * MINUTE_SECS
OPEN_LOCK_TTL = 5 * MINUTE_SECS


@dataclass(frozen=True)
class Initiative:
    slug: str
    size: int
    # ``(size, site)`` -> ``[[edition key, readers], ...]``, most-read first. None when the list is frozen by whoever defines it.
    pick: Callable[[int, object], list[list]] | None
    # The fields it asks about: its filters, its progress figure and its "Surprise me" draw from these.
    fields: tuple[str, ...]
    # As typed by whoever set it up, so untranslated; blank on a built-in one, whose name ``describe`` translates.
    title: str = ""
    description: str = ""
    # No start means a draft. From ``ends_at`` on it hands out no more tasks, but stays listed with its final figures.
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    # Off the public pages whatever its dates; its saves and stats carry on.
    hidden: bool = False
    featured: bool = False

    @property
    def store_key(self) -> str:
        return f"contribute-initiative-{self.slug}"

    def status(self, now: datetime | None = None) -> str:
        """``draft``, ``scheduled``, ``live`` or ``ended``. Derived from the dates on every read, so a start date is a schedule."""
        now = now or datetime.now(UTC)
        if self.starts_at is None:
            return "draft"
        if now < self.starts_at:
            return "scheduled"
        return "ended" if self.ends_at is not None and now >= self.ends_at else "live"


# Most shelvings name the edition (61% of all, 73% for the most-read books, 2026-10), so the reading log can pick the copy people read.
# A book's editions often take more than one of the top spots; this many per work keeps the list from filling with near-duplicates.
EDITIONS_PER_WORK = 2
# Ask for more than needed: some top editions have no ISBN, and the per-work cap drops others.
OVERFETCH = 3


def with_open_gap(picks: list[list], site, fields: tuple[str, ...], taken_works: set[str]) -> list[list]:
    """Of ``[key, readers]`` picks, the editions with something still to fill in ``fields``, one per work.

    A work field reads the edition's work; ``taken_works`` grows with the works kept, so a later call skips their other editions.
    """
    kept = []
    for i in range(0, len(picks), 100):
        chunk = picks[i : i + 100]
        editions = {e.key: e for e in site.get_many([key for key, _readers in chunk])}
        work_keys = [w.key for e in editions.values() if (w := tasks.work_of(e))]
        works = {w.key: w for w in site.get_many(work_keys)} if work_keys else {}
        for key, readers in chunk:
            if not (edition := editions.get(key)):
                continue
            work = tasks.work_of(edition)
            if work is not None and work.key in taken_works:
                continue
            if any(tasks.is_missing(edition, f, works.get(work.key) if work is not None else None) for f in fields):
                kept.append([key, readers])
                if work is not None:
                    taken_works.add(work.key)
    return kept


def pick_most_shelved(size: int, site, per_work: int = EDITIONS_PER_WORK, fields: tuple[str, ...] | None = None) -> list[list]:
    """The editions people name most when they shelve a book: ISBN editions only, at most ``per_work`` per work, and with
    ``fields`` only those that still have a gap in one of them (which are work fields, so then one edition per work).

    Tops up from ``pick_most_read`` when the reading log names too few editions, as on a dev database.
    """
    rows = Bookshelves.most_logged_editions_sync(size * OVERFETCH)
    picks: list[list] = []
    taken_works: set[str] = set()
    counted: Counter[int] = Counter()
    for i in range(0, len(rows), 100):
        chunk = rows[i : i + 100]
        editions = {e.key: e for e in site.get_many([f"/books/OL{r['edition_id']}M" for r in chunk])}
        wanted = []
        for r in chunk:
            edition = editions.get(f"/books/OL{r['edition_id']}M")
            if not edition or edition.type.key != "/type/edition" or not (edition.get("isbn_13") or edition.get("isbn_10")):
                continue
            if counted[r["work_id"]] >= per_work:
                continue
            counted[r["work_id"]] += 1
            wanted.append([edition.key, r["readers"]])
        picks += with_open_gap(wanted, site, fields, taken_works) if fields else wanted
        if len(picks) >= size:
            return picks[:size]
    taken = {p[0] for p in picks}
    more = [p for p in pick_most_read(size, site) if p[0] not in taken]
    return picks + (with_open_gap(more, site, fields, taken_works) if fields else more)[: size - len(picks)]


def pick_most_read(size: int, site=None) -> list[list]:
    """The most-read works with an ISBN edition, one edition each: the one search would show first, without its cover boost.

    Search ranks a work's editions by language, ebook access and cover; a cover boost here would favour editions with fewer gaps.
    """
    has_isbn = "type:edition AND isbn:*"
    result = get_solr().select(
        f"type:work AND {{!parent which=type:work v='{has_isbn}'}}",
        fields=["key", "readinglog_count", "editions:[subquery]"],
        rows=size,
        sort="readinglog_count desc",
        editions_q="({!terms f=_root_ v=$row.key}) AND ({!edismax v=$edAll bq=$edBoost})",
        editions_edAll="*:*",
        editions_edBoost="language:eng^40 ebook_access:public^10 ebook_access:borrowable^8 ebook_access:printdisabled^2",
        editions_fq=has_isbn,
        editions_fl="key",
        editions_rows=1,
        _timeout=PICK_TIMEOUT_SECONDS,
        _pass_time_allowed=False,
        request_label="CONTRIBUTE_INITIATIVE",
    )
    if result.partial:
        raise TimeoutError("Solr returned part of the initiative; not freezing it")
    return [[d["editions"]["docs"][0]["key"], d.get("readinglog_count")] for d in result.docs if d.get("editions", {}).get("docs")]


TAG_FIELDS = (LITERARY_FORMS, GENRES)


def pick_untagged_works(size: int, site) -> list[list]:
    """The most-read works still missing their literary form or genres, one edition each: the tags live on the work."""
    return pick_most_shelved(size, site, per_work=1, fields=TAG_FIELDS)


# The initiatives defined here; the store adds to them and overrides them. A new list is a new slug: the old one stays in the store for comparison.
BUILTIN_START = datetime(2026, 11, 1, tzinfo=UTC)
MOST_READ = Initiative(
    "most-read-2026-11", 2000, pick_most_shelved, ("covers", "languages", "number_of_pages", "publishers"), starts_at=BUILTIN_START, featured=True
)
TAGS = Initiative("genres-2026-11", 2000, pick_untagged_works, TAG_FIELDS, starts_at=BUILTIN_START)
BUILTIN = (MOST_READ, TAGS)

DEFINITION_TYPE = "contribute-project"
DEFINITIONS_TTL = MINUTE_SECS


def definition_key(slug: str) -> str:
    return f"{DEFINITION_TYPE}-{slug}"


def read_definitions(site) -> list[dict]:
    """Every initiative's definition doc, straight from the store."""
    return site.store.values(type=DEFINITION_TYPE, limit=1000)


@cache.memoize(engine="memcache", key="contribute.definitions", expires=DEFINITIONS_TTL)
def cached_definitions() -> list[dict]:
    """The definition docs as every request reads them: a change shows within ``DEFINITIONS_TTL``."""
    return read_definitions(request_site.get())


class Conflict(Exception):
    """The definition changed after the caller read it, so their change wasn't made."""


# Enough to see who did what for a long while, without the doc every request reads growing forever.
LOG_LIMIT = 200


def definition_doc(site, slug: str) -> dict:
    """The initiative's definition doc as stored, {} when it has none: a built-in one nobody has changed."""
    return site.store.get(definition_key(slug)) or {}


def definition_rev(site, slug: str) -> str:
    """The definition doc's revision, "" when there is none yet. A change names the one it was made against."""
    return definition_doc(site, slug).get("_rev", "")


def change(site, slug: str, changes: dict, by: str, action: str, rev: str) -> None:
    """Set ``changes`` on the initiative's definition, noting who did it in the doc's own log: store docs keep no history.

    ``rev`` is the revision the caller saw. If the doc has moved on since, nothing is written and ``Conflict`` is raised,
    so two people changing one project can't silently undo each other.
    """
    key = definition_key(slug)
    doc = dict(definition_doc(site, slug) or {"type": DEFINITION_TYPE, "slug": slug})
    if doc.get("_rev", "") != rev:
        raise Conflict(slug)
    entry = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "by": by, "action": action, "changes": changes}
    doc |= changes
    doc["log"] = [*doc.get("log", []), entry][-LOG_LIMIT:]
    try:
        site.store[key] = doc
    except ClientException as e:
        # The store checks the revision again as it writes, which catches a change made since the read above.
        raise Conflict(slug) from e
    cache.get_memcache().delete("contribute.definitions")


def set_headline(site, slug: str, by: str, rev: str) -> None:
    """Make ``slug`` the featured initiative and unfeature the rest, so there is one headline."""
    change(site, slug, {"featured": True}, by, "headline", rev)
    for other in every(read_definitions(site)):
        if other.featured and other.slug != slug:
            change(site, other.slug, {"featured": False}, by, "unheadline", definition_rev(site, other.slug))


def parse_time(raw) -> datetime | None:
    """A stored ISO time as UTC, taken as UTC when it names no zone; None for a blank or a value that isn't one."""
    try:
        when = datetime.fromisoformat(raw) if raw else None
    except TypeError, ValueError:
        return None
    return (when.replace(tzinfo=UTC) if when.tzinfo is None else when.astimezone(UTC)) if when else None


def from_definition(doc: dict, base: Initiative | None = None) -> Initiative | None:
    """The initiative ``doc`` defines, or ``base`` with the keys ``doc`` names changed.

    A doc that can't be one (no slug, no title of its own, no fields Tasks knows) is skipped rather than raised, so it
    can't take /tasks down: the answer is then ``base``, which is None for a new slug.
    """
    slug = doc.get("slug")
    if not (start := base or (Initiative(slug, 0, None, ()) if slug and isinstance(slug, str) else None)):
        return None
    changes: dict = {}
    if doc.get("title"):
        changes |= {"title": str(doc["title"]), "description": str(doc.get("description") or "")}
    if "fields" in doc:
        changes["fields"] = tuple(f for f in doc["fields"] or () if f in tasks.POINTS)
    if isinstance(doc.get("size"), int):
        changes["size"] = doc["size"]
    changes |= {key: parse_time(doc[key]) for key in ("starts_at", "ends_at") if key in doc}
    changes |= {key: bool(doc[key]) for key in ("hidden", "featured") if key in doc}
    initiative = replace(start, **changes)
    if not initiative.fields or not (base or initiative.title):
        logger.warning("Skipping the initiative definition %r", slug)
        return base
    return initiative


def every(definitions: list[dict] | None = None) -> list[Initiative]:
    """All initiatives whatever their status: the built-in ones as the store changes them, then the store's own, earliest start first.

    A built-in one the store doesn't mention is the very object defined above.
    """
    docs = {d["slug"]: d for d in (cached_definitions() if definitions is None else definitions) if isinstance(d.get("slug"), str)}
    builtin = [from_definition(docs.pop(b.slug), b) or b if b.slug in docs else b for b in BUILTIN]
    stored = [i for doc in docs.values() if (i := from_definition(doc))]
    far = datetime.max.replace(tzinfo=UTC)
    return builtin + sorted(stored, key=lambda i: (i.starts_at or far, i.slug))


def started(definitions: list[dict] | None = None) -> list[Initiative]:
    """The initiatives with saves and stats to count: live or ended, hidden or not."""
    return [i for i in every(definitions) if i.status() in ("live", "ended")]


def listed() -> list[Initiative]:
    """The initiatives the public pages show: live or ended, and not hidden."""
    return [i for i in started() if not i.hidden]


def running() -> list[Initiative]:
    """The listed initiatives still handing out tasks."""
    return [i for i in listed() if i.status() == "live"]


def headline() -> Initiative:
    """The one /tasks opens on: the featured running initiative, else the first running, else the first listed."""
    on = running()
    return next((i for i in on if i.featured), None) or next(iter(on or listed()), MOST_READ)


def describe(initiative: Initiative) -> dict[str, str]:
    """An initiative's name and pitch, as Tasks and the stats page show them: the name says the job, the pitch which books and what they need.

    Both draw on the most-shelved books, so the job is what tells them apart; the book count goes in the dashboard's fine print.
    Names are title case: a project is a proper name, unlike the sentence-case labels around it.
    """
    if initiative.title:
        return {"title": initiative.title, "description": initiative.description}
    if initiative.slug == TAGS.slug:
        return {
            "title": _("Sort the Stacks"),
            "description": _("Mark the books people shelve most as fiction or nonfiction, and pick their genres."),
        }
    return {
        "title": _("Fill the Gaps"),
        "description": _("Add missing covers, page counts, publishers and languages to the books people shelve most."),
    }


def fine_print(initiative: Initiative, site) -> str:
    """The line under the dashboard's pitch: how many books, and when the list was picked."""
    books = ungettext("%(count)s book", "%(count)s books", initiative.size, count=commify(initiative.size))
    if started := started_at(initiative, site):
        return _("%(books)s · Started %(date)s", books=books, date=format_date(started))
    return books


def get(slug: str, hidden: bool = False) -> Initiative | None:
    """The listed initiative with this slug; with ``hidden``, a hidden one too, for a save that began before it was hidden."""
    return next((i for i in (started() if hidden else listed()) if i.slug == slug), None)


def load_frozen(initiative: Initiative, site) -> list[list] | None:
    """The frozen list from the store, or None if it hasn't been picked yet. Never picks."""
    if doc := site.store.get(initiative.store_key):
        return doc["editions"]
    return None


_started: dict[str, datetime] = {}


def started_at(initiative: Initiative, site) -> datetime | None:
    """When the list was picked, or None before then. Kept once read: it never changes, and the doc carries the whole list."""
    if initiative.slug not in _started and (doc := site.store.get(initiative.store_key)):
        _started[initiative.slug] = datetime.fromisoformat(doc["frozen_at"])
    return _started.get(initiative.slug)


def load_or_freeze(initiative: Initiative, site) -> list[list]:
    """The frozen list from the store; the first call picks it and stores it."""
    if (editions := load_frozen(initiative, site)) is not None:
        return editions
    # One with no picker has its list frozen when it is set up; until then it has no books.
    editions = initiative.pick(initiative.size, site) if initiative.pick else []
    if editions:
        site.store[initiative.store_key] = {
            "type": "contribute-initiative",
            "slug": initiative.slug,
            "frozen_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "editions": editions,
        }
    return editions


def not_found_fields(site) -> dict[str, set[str]]:
    """Fields enough people couldn't find, by edition key."""
    found: dict[str, set[str]] = {}
    for doc in site.store.values(type=NOT_FOUND_TYPE, limit=100_000):
        # A mark for a field no longer on offer has no threshold; leave it be.
        if (threshold := NOT_FOUND_PEOPLE.get(doc["field"])) and len(doc.get("people", [])) >= threshold:
            found.setdefault(doc["edition"], set()).add(doc["field"])
    return found


def build_gaps(initiative: Initiative, site, batch: int = 100) -> list[list]:
    """Every edition on the list as ``[key, readers, open fields, fields nobody could find]``, picking the list if needed."""
    return gaps_for(load_or_freeze(initiative, site), site, batch)


def gaps_for(picks: list[list], site, batch: int = 100) -> list[list]:
    """Gaps for an already-loaded list of ``[key, readers]`` picks, read from the database."""
    unfindable = not_found_fields(site)
    rows = []
    for i in range(0, len(picks), batch):
        chunk = picks[i : i + batch]
        editions = {e.key: e for e in site.get_many([key for key, _readers in chunk])}
        # The work fields read each edition's work; one fetch for the chunk rather than one per edition.
        work_keys = [w.key for e in editions.values() if (w := tasks.work_of(e))]
        works = {w.key: w for w in site.get_many(work_keys)} if work_keys else {}
        for key, readers in chunk:
            # A merged or deleted edition has nothing left to fill.
            if not (edition := editions.get(key)) or edition.type.key != "/type/edition":
                continue
            work = tasks.work_of(edition)
            missing = [t.field for t in tasks.tasks_for_edition(edition, works.get(work.key) if work else None)]
            skipped = unfindable.get(key, set())
            rows.append([key, readers, [f for f in missing if f not in skipped], [f for f in missing if f in skipped]])
    return rows


def build_gaps_in_thread(initiative: Initiative) -> list[list]:
    """The rebuild as the pool's thread runs it: on a fresh anonymous site, which the thread also gets as its request site.

    The request's own site carries the visitor's auth token and cache, so the thread must not share it; the tag vocabulary
    the work fields read goes through the request site, so the thread needs one set.
    """
    site = create_site()
    token = request_site.set(site)
    try:
        return build_gaps(initiative, site)
    finally:
        request_site.reset(token)


def get_gaps(initiative: Initiative) -> list[list] | None:
    """The shared gaps for ``initiative``, or None while the first build (and on a new initiative, the pick) runs."""
    return pool.get(f"contribute.initiative:{initiative.slug}", OPEN_TTL, lambda: build_gaps_in_thread(initiative), lock_ttl=OPEN_LOCK_TTL, keep=DAY_SECS)


def progress(gaps: list[list], fields: tuple[str, ...]) -> dict[str, int]:
    """How far an initiative has come: editions with nothing left to fill, out of all of them, the gaps still open, and the
    share of details filled. A detail nobody could find counts as filled, so every save or "couldn't find it" moves it.
    Only ``fields`` count, the initiative's own; the gaps keep the rest for the unlinked filters."""
    wanted = set(fields)
    open_count = sum(1 for _key, _readers, open_fields, _skipped in gaps for f in open_fields if f in wanted)
    slots = len(gaps) * len(wanted)
    return {
        "done": sum(1 for _key, _readers, open_fields, _skipped in gaps if not wanted.intersection(open_fields)),
        "total": len(gaps),
        "open": open_count,
        "not_found": sum(1 for _key, _readers, _open, skipped in gaps for f in skipped if f in wanted),
        # Rounded down, so it only reads 100 when nothing is left.
        "percent": (slots - open_count) * 100 // slots if slots else 0,
    }


def record_not_found(site, edition_key: str, fld: str, user_key: str) -> None:
    """Note that ``user_key`` looked for ``fld`` on the edition and couldn't find it. Kept apart from the record, so it isn't an edit."""
    key = f"{NOT_FOUND_TYPE}-{edition_key.rsplit('/', maxsplit=1)[-1]}-{fld}"
    doc = site.store.get(key) or {"type": NOT_FOUND_TYPE, "edition": edition_key, "field": fld, "people": []}
    if user_key not in doc["people"]:
        doc["people"] = [*doc["people"], user_key]
        site.store[key] = doc
