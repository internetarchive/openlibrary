"""An initiative: a fixed list of editions that Tasks works through, and the fields it asks about.

The list is picked once and frozen in the store, and what it had open then is kept, so progress counts up from 0% as the
gaps open at the start close, not against a pool that drifts as books get fixed.
Nothing builds it by hand: the first request after a deploy starts the pick on a background thread, as ``pool`` does.
Several initiatives run at once; ``/tasks`` opens on ``headline()`` and the others are a click away.

What an initiative is (its name, fields, dates, whether it is hidden) lives in the store too, in a small doc apart from
the list, so it changes without a deploy. ``BUILTIN`` holds the ones defined here; a store doc with the same slug overrides
the keys it names, and a doc with a new slug is a new initiative.
"""

import functools
import logging
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta

from infogami.infobase.client import ClientException
from infogami.utils.delegate import create_site
from openlibrary.contribute import pool, tasks
from openlibrary.core import admin, cache
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
# The share of the tasks open at the start that counts as success. Not 100: some gaps can't be filled, and the last few
# cost far more than the rest. A project can set its own.
DEFAULT_GOAL = 90
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
    # The percent (see ``progress``) at which the project has reached its goal; it keeps counting past it.
    goal: int = DEFAULT_GOAL
    # What was open when the list was frozen, so progress counts up from 0%: ``{"open": n, "fields": {field: {"open": n,
    # "not_found": n}}}``. None until the first gaps build records it (``record_start``).
    start: dict | None = field(default=None, hash=False, compare=False)

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
    """Of ``[key, readers]`` picks, the editions with something still to fill in ``fields``; one per work when all of those live on the work.

    A work field reads the edition's work; ``taken_works`` grows with the works kept, so a later call skips their other editions.
    """
    one_per_work = tasks.WORK_FIELDS.issuperset(fields)
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
            if one_per_work and work is not None and work.key in taken_works:
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


def is_builtin(initiative: Initiative) -> bool:
    return any(b.slug == initiative.slug for b in BUILTIN)


def make_picker(name: str, fields: tuple[str, ...]) -> Callable[[int, object], list[list]] | None:
    """The picker a stored definition names. Its list is then picked and frozen on the first read, on the pool's thread, as a built-in one's is.

    ``most-shelved-missing`` keeps only books with a gap in ``fields``; when all of those live on the work, one edition per work.
    """
    if name == "most-shelved":
        return pick_most_shelved
    if name == "most-shelved-missing":
        return functools.partial(pick_most_shelved, per_work=1 if tasks.WORK_FIELDS.issuperset(fields) else EDITIONS_PER_WORK, fields=fields)
    return None


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
    entry = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "by": by, "action": action, "changes": {} if action == "create" else changes}
    doc |= changes
    doc["log"] = [*doc.get("log", []), entry][-LOG_LIMIT:]
    try:
        site.store[key] = doc
    except ClientException as e:
        # The store checks the revision again as it writes, which catches a change made since the read above.
        raise Conflict(slug) from e
    cache.get_memcache().delete("contribute.definitions")


def freeze(site, initiative: Initiative, editions: list[list]) -> None:
    """Store ``editions`` as the initiative's list."""
    site.store[initiative.store_key] = {
        "type": "contribute-initiative",
        "slug": initiative.slug,
        "frozen_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "editions": editions,
    }
    cache.get_memcache().delete(started_key(initiative.slug))


def gaps_key(slug: str) -> str:
    return f"contribute.initiative:{slug}"


def make_slug(title: str, taken: set[str], today: datetime | None = None) -> str:
    """A slug nothing else has: the title in lowercase with hyphens, the month it was made, and a number if that is taken.

    It never changes afterwards: saves, stats and URLs all name the project by it.
    """
    today = today or datetime.now(UTC)
    words = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-") or "project"
    base = f"{words}-{today:%Y-%m}"
    return next(s for s in (base, *(f"{base}-{n}" for n in range(2, 1000))) if s not in taken)


def create(site, definition: dict, editions: list[list] | None, by: str) -> Initiative:
    """Set up a new initiative from ``definition`` (title, description, fields, dates, and a picker if it has one), with
    ``editions`` as its list when whoever made it named the books. Returns it as the registry will read it."""
    slug = make_slug(definition["title"], {i.slug for i in every(read_definitions(site))} | {"new"})
    doc = {"type": DEFINITION_TYPE, "slug": slug} | definition
    if not (initiative := from_definition(doc)):
        raise ValueError("Not a definition Tasks can run")
    if editions is not None:
        freeze(site, initiative, editions)
    change(site, slug, definition, by, "create", rev="")
    return initiative


def delete(site, initiative: Initiative) -> None:
    """Remove an initiative set up in the store, with its list and its shared gaps. Its saves, if it ever had any, keep its slug."""
    for key in (definition_key(initiative.slug), initiative.store_key):
        if site.store.get(key):
            del site.store[key]
    mc = cache.get_memcache()
    for key in ("contribute.definitions", gaps_key(initiative.slug), pool.lock_key(gaps_key(initiative.slug)), started_key(initiative.slug)):
        mc.delete(key)


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
    if isinstance(doc.get("goal"), int) and 1 <= doc["goal"] <= 100:
        changes["goal"] = doc["goal"]
    if isinstance(doc.get("start"), dict):
        changes["start"] = doc["start"]
    initiative = replace(start, **changes)
    if not base and (picker := make_picker(str(doc.get("picker") or ""), initiative.fields)):
        initiative = replace(initiative, pick=picker)
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
    """The initiatives the public pages show: live or ended, and not hidden. The live ones come first."""
    return sorted((i for i in started() if not i.hidden), key=lambda i: i.status() == "ended")


def running() -> list[Initiative]:
    """The listed initiatives still handing out tasks."""
    return [i for i in listed() if i.status() == "live"]


def headline() -> Initiative:
    """The one /tasks opens on: the featured running initiative, else the first running, else the first listed, else the
    built-in most-read one as the store has changed it, so there is always one to open."""
    on = running()
    if found := next((i for i in on if i.featured), None) or next(iter(on or listed()), None):
        return found
    return next((i for i in every() if i.slug == MOST_READ.slug), MOST_READ)


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


def last_day(ends_at: datetime | None) -> date | None:
    """The last day a project runs. An end date is stored as the midnight after it, and a stop as the moment it happened."""
    return (ends_at - timedelta(microseconds=1)).date() if ends_at else None


def fine_print(initiative: Initiative, site) -> str:
    """The line under the dashboard's pitch: when it runs and how many books."""
    started = started_at(initiative, site)
    ended = last_day(initiative.ends_at)
    parts = []
    if started and ended:
        start, end = format_date(started), format_date(datetime.combine(ended, time()))
        if initiative.status() == "ended":
            parts.append(_("Ran %(start)s to %(end)s", start=start, end=end))
        else:
            parts.append(_("Started %(start)s, ends %(end)s", start=start, end=end))
    elif started:
        parts.append(_("Started %(date)s", date=format_date(started)))
    parts.append(ungettext("%(count)s book", "%(count)s books", initiative.size, count=commify(initiative.size)))
    return " · ".join(parts)


def get(slug: str, hidden: bool = False) -> Initiative | None:
    """The listed initiative with this slug; with ``hidden``, a hidden one too, for a save that began before it was hidden."""
    return next((i for i in (started() if hidden else listed()) if i.slug == slug), None)


def load_frozen(initiative: Initiative, site) -> list[list] | None:
    """The frozen list from the store, or None if it hasn't been picked yet. Never picks."""
    if doc := site.store.get(initiative.store_key):
        return doc["editions"]
    return None


_started: dict[str, datetime] = {}


def started_key(slug: str) -> str:
    return f"contribute.started:{slug}"


def started_at(initiative: Initiative, site) -> datetime | None:
    """When the list was picked, or None before then. The doc carries the whole list, so the date is kept once read: in
    the process for a built-in one, whose date never changes, and in memcache for one set up in the store, which
    ``freeze`` and ``delete`` clear, since it can be deleted and made again."""
    if initiative.slug in _started:
        return _started[initiative.slug]
    mc = cache.get_memcache()
    if not is_builtin(initiative) and (kept := mc.get(started_key(initiative.slug))):
        return datetime.fromisoformat(kept)
    if not (doc := site.store.get(initiative.store_key)):
        return None
    when = datetime.fromisoformat(doc["frozen_at"])
    if is_builtin(initiative):
        _started[initiative.slug] = when
    else:
        mc.set(started_key(initiative.slug), doc["frozen_at"])
    return when


def load_or_freeze(initiative: Initiative, site) -> list[list]:
    """The frozen list from the store; the first call picks it and stores it."""
    if (editions := load_frozen(initiative, site)) is not None:
        return editions
    # One with no picker has its list frozen when it is set up; until then it has no books.
    editions = initiative.pick(initiative.size, site) if initiative.pick else []
    if editions:
        freeze(site, initiative, editions)
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
    """Every edition on the list as ``[key, readers, open fields, fields nobody could find, work key]``, picking the list if needed."""
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
            rows.append([key, readers, [f for f in missing if f not in skipped], [f for f in missing if f in skipped], work.key if work is not None else None])
    return rows


def build_gaps_in_thread(initiative: Initiative) -> list[list]:
    """The rebuild as the pool's thread runs it: on a fresh anonymous site, which the thread also gets as its request site.

    The request's own site carries the visitor's auth token and cache, so the thread must not share it; the tag vocabulary
    the work fields read goes through the request site, so the thread needs one set.
    """
    site = create_site()
    token = request_site.set(site)
    try:
        gaps = build_gaps(initiative, site)
        if gaps and not initiative.start:
            record_start(initiative, site, gaps)
        return gaps
    finally:
        request_site.reset(token)


def first_counted_open(initiative: Initiative, site) -> int | None:
    """The open details the stats job first counted for the initiative, the first point of its "Tasks left" line; None if it never has."""
    if not (frozen := site.store.get(initiative.store_key)):
        return None
    days = (date.today() - datetime.fromisoformat(frozen["frozen_at"]).date()).days + 1
    counts = (admin.initiative_counts(doc).get(initiative.slug, {}) for doc in admin.read_count_docs(site, max(days, 1)))
    return next((c["open"] for c in counts if "open" in c), None)


def record_start(initiative: Initiative, site, gaps: list[list]) -> None:
    """Store what is open now as where the initiative started, once. One that ran before starts were recorded takes its
    total from the stats job's first count, so the work done since still shows; its per-detail figures can only be today's."""
    doc = definition_doc(site, initiative.slug)
    # Gone, or a stored one deleted while this build ran: writing would bring back a doc with no title.
    if doc.get("start") or (not doc and not is_builtin(initiative)):
        return
    counts = {f: field_counts(gaps, f) for f in set(initiative.fields)}
    still_open = sum(c["open"] for c in counts.values())
    first = first_counted_open(initiative, site)
    start = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "open": still_open if first is None else first,
        "fields": {f: {"open": c["open"], "not_found": c["not_found"]} for f, c in counts.items()},
    }
    try:
        site.store[definition_key(initiative.slug)] = (doc or {"type": DEFINITION_TYPE, "slug": initiative.slug}) | {"start": start}
    except ClientException:
        # Someone changed the definition as this wrote; the next build tries again.
        logger.info("Could not record where %s started", initiative.slug)
        return
    cache.get_memcache().delete("contribute.definitions")


def get_gaps(initiative: Initiative) -> list[list] | None:
    """The shared gaps for ``initiative``, or None while the first build (and on a new initiative, the pick) runs."""
    return pool.get(gaps_key(initiative.slug), OPEN_TTL, lambda: build_gaps_in_thread(initiative), lock_ttl=OPEN_LOCK_TTL, keep=DAY_SECS)


def field_counts(gaps: list[list], fld: str) -> dict[str, int]:
    """One field across the gaps: how many it is asked of, still open, and nobody could find.

    An edition field is asked of every edition. A work field is asked once per work, however many of its editions are
    listed: open while any of them has it open, since one answer fills it for all.
    """
    if fld not in tasks.WORK_FIELDS:
        return {
            "total": len(gaps),
            "open": sum(1 for row in gaps if fld in row[2]),
            "not_found": sum(1 for row in gaps if fld in row[3]),
        }
    # A row cached before rows carried the work, or an orphan edition, stands for itself.
    works, still_open, not_found = set(), set(), set()
    for row in gaps:
        work = (row[4] if len(row) > 4 else None) or row[0]
        works.add(work)
        if fld in row[2]:
            still_open.add(work)
        elif fld in row[3]:
            not_found.add(work)
    not_found -= still_open
    return {"total": len(works), "open": len(still_open), "not_found": len(not_found)}


def closed_share(start: int, still_open: int) -> int:
    """The percent of ``start`` open details closed since. Rounded down, so it only reads 100 when nothing is left, and
    never below 0, which a detail emptied after the start would otherwise push it to."""
    if not start:
        return 0 if still_open else 100
    return max(0, (start - still_open) * 100 // start)


def progress(gaps: list[list], fields: tuple[str, ...], start: dict | None = None, goal: int = DEFAULT_GOAL) -> dict:
    """How far an initiative has come: editions with nothing left to fill, out of all of them, the gaps still open, and the
    share of the gaps open at ``start`` (``Initiative.start``) closed since; without one, today is the start.
    A detail nobody could find counts as closed, so every save or "couldn't find it" moves it.
    Only ``fields`` count, the initiative's own; the gaps keep the rest for the unlinked filters. A work field counts
    once per work (see ``field_counts``), so one answer is one gap closed. ``reached`` is whether the percent has met ``goal``."""
    wanted = set(fields)
    counts = [field_counts(gaps, f) for f in wanted]
    open_count = sum(c["open"] for c in counts)
    began = start["open"] if start and "open" in start else open_count
    percent = closed_share(began, open_count)
    return {
        "done": sum(1 for row in gaps if not wanted.intersection(row[2])),
        "total": len(gaps),
        "open": open_count,
        "not_found": sum(c["not_found"] for c in counts),
        "start": began,
        "percent": percent,
        "goal": goal,
        "reached": percent >= goal,
    }


NOTE_MAX = 500
"""The longest "couldn't find it" note kept; the task form's textarea stops at it too."""


def record_not_found(site, edition_key: str, fld: str, user_key: str, note: str = "") -> None:
    """Note that ``user_key`` looked for ``fld`` on the edition and couldn't find it. Kept apart from the record, so it isn't an edit.

    ``note`` is their comment (where they looked, say), kept by person; a later one replaces theirs.
    """
    key = f"{NOT_FOUND_TYPE}-{edition_key.rsplit('/', maxsplit=1)[-1]}-{fld}"
    doc = site.store.get(key) or {"type": NOT_FOUND_TYPE, "edition": edition_key, "field": fld, "people": []}
    changed = user_key not in doc["people"]
    if changed:
        doc["people"] = [*doc["people"], user_key]
    if (note := note.strip()[:NOTE_MAX]) and doc.get("notes", {}).get(user_key) != note:
        doc["notes"] = doc.get("notes", {}) | {user_key: note}
        changed = True
    if changed:
        site.store[key] = doc


def containing(edition_key: str, fld: str, lead: Initiative) -> Initiative | None:
    """The running initiative a task belongs to, for a task link that doesn't name one. Headline links are bare too, so the
    headline ``lead`` keeps any book on its list, and while its gaps are still building; only a book it doesn't list goes to
    the first other initiative that lists it and asks for ``fld``. None leaves the task with the headline."""
    if (lead_gaps := get_gaps(lead)) is None or any(row[0] == edition_key for row in lead_gaps):
        return None
    for initiative in running():
        if initiative.slug != lead.slug and fld in initiative.fields and (gaps := get_gaps(initiative)) and any(row[0] == edition_key for row in gaps):
            return initiative
    return None
