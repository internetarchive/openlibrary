"""The public /tasks page's "happening now" feed: recent edits as rows.

``recent_rows`` rotates through a pool of real recent edits, restamped back from now. The pool is
rebuilt from recentchanges at most every ``POOL_TTL`` and shared via memcache through ``pool``, so no
request ever builds it; while it's empty the feed is too.
"""

import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from itertools import zip_longest

from infogami.utils.delegate import create_site
from openlibrary.contribute import pool
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream.utils import get_coverstore_public_url

logger = logging.getLogger("openlibrary.contribute.feed")

# Only edits to catalog records make the feed; accounts, lists and store writes don't.
RECORD_PREFIXES = ("/books/", "/works/", "/authors/")
# Seconds between rows when restamping, so a rotation reads like a quiet afternoon of edits.
ROW_SPACING = 47

# recentchanges filters one kind per query, and these are the kinds worth showing. Most non-bot
# changes are account signups, so asking for these directly is far cheaper than filtering a firehose.
POOL_KINDS = ("edit-book", "add-cover", "add-book")
POOL_PER_KIND = 100
# Only this many days back. The date bounds the query's walk down the transaction table; without it,
# a kind that humans rarely do (add-cover) has Postgres scanning back through bot traffic for a long time.
POOL_DAYS = 7
POOL_SIZE = 200
# Versioned: the unversioned key still holds entries in the old feed code's shape.
POOL_KEY = "contribute.feed_pool.v2"
POOL_TTL = 20 * 60
POOL_LOCK_KEY = pool.lock_key(POOL_KEY)
REFRESH_THREAD_NAME = pool.thread_name(POOL_KEY)
# Kinds whose comment is a system default (a cover URL, "Added new book.") rather than the editor's words.
DEFAULT_COMMENT_KINDS = ("add-book", "add-cover")


def kind_labels() -> dict[str, str]:
    """What the row says was done, by changeset kind. Kinds not listed here stay out of the feed."""
    return {
        "edit-book": _("Edited this book"),
        "add-book": _("Added this book"),
        "add-cover": _("Added a cover"),
        "merge-authors": _("Merged duplicate authors"),
        "merge-works": _("Merged duplicate works"),
        "update": _("Updated this record"),
        "edit-author": _("Edited this author"),
        "undo": _("Reverted an edit"),
    }


def clean_comment(comment: str, limit: int = 90) -> str:
    """A comment worth showing instead of the kind label: short prose, not a pasted URL or key."""
    comment = (comment or "").strip()
    if not comment or len(comment) > limit or "://" in comment or comment.startswith("/"):
        return ""
    return comment


def cover_url(cover_id: int | None, size: str = "M") -> str:
    return f"{get_coverstore_public_url()}/b/id/{cover_id}-{size}.jpg" if cover_id and cover_id > 0 else ""


def build_row(*, id: str, key: str, title: str, authors: str, cover_id: int | None, kind: str, editor: str, editor_key: str, comment: str) -> dict:
    """A pool item; ``rotate`` adds the translated action and the timestamp when the row is served."""
    return {
        "id": id,
        "key": key,
        "title": title,
        "authors": authors,
        "cover_url": cover_url(cover_id),
        "kind": kind,
        "editor": editor,
        "editor_key": editor_key,
        "comment": comment,
    }


def rotate(items: list[dict], limit: int, offset: int, now: datetime | None, make_id: Callable[[int], str]) -> list[dict]:
    """``limit`` items from ``offset``, wrapping around, newest first and timestamped back from ``now``."""
    now = now or datetime.now(UTC)
    labels = kind_labels()
    rows = []
    for i in range(limit):
        index = (offset + i) % len(items)
        stamp = now - timedelta(seconds=ROW_SPACING * i + random.randint(0, 20))
        # The label and anonymous editor are translated per request; the pool is shared across languages.
        item = items[index]
        rows.append(
            item
            | {
                "id": make_id(index),
                "editor": item["editor"] or _("a visitor"),
                "action": labels.get(item["kind"], _("Updated this record")),
                "timestamp": stamp.isoformat(timespec="seconds"),
            }
        )
    return rows


def recent_rows(limit: int, offset: int = 0, now: datetime | None = None) -> list[dict]:
    """Real recent edits from the shared pool, rotated and restamped; none while the pool is empty."""
    if not (pool := get_pool()):
        return []
    return rotate(pool, limit, offset, now, lambda i: pool[i]["id"])


def get_pool() -> list[dict]:
    """The cached pool, stale or not; empty while a cold cache fills in the background."""
    # A fresh anonymous site for the thread: the request's carries the visitor's auth token and its own cache.
    return pool.get(POOL_KEY, POOL_TTL, lambda: build_pool(create_site())) or []


def record_key(change) -> str:
    """The catalog record a changeset is about: its book, else its work, else its author. A book edit can touch all three."""
    keys = [c["key"] for c in change.changes]
    return next((k for prefix in RECORD_PREFIXES for k in keys if k.startswith(prefix)), "")


def record_title(thing) -> str:
    """Editions and works have a title; authors a name."""
    return thing.get("title") or thing.get("name") or ""


def record_cover_id(thing) -> int | None:
    covers = as_list(thing.get("covers"))
    return next((c for c in covers if isinstance(c, int) and c > 0), None)


def ref_key(ref) -> str:
    """The key of an author or work reference, or of a work's embedded ``{"author": ...}`` entry (a keyless Thing), without loading it."""
    return getattr(ref, "key", None) or getattr(getattr(ref, "author", None), "key", None) or ""


def as_list(value) -> list:
    """Infogami hands back list fields as plain or lazy lists, or None."""
    return list(value) if value else []


def author_refs(thing, works: dict) -> list:
    """An edition's own authors, else its work's."""
    if refs := as_list(thing.get("authors")):
        return refs
    work_refs = as_list(thing.get("works"))
    work = works.get(ref_key(work_refs[0])) if work_refs else None
    return as_list(work.get("authors")) if work else []


def fetch_things(site, keys) -> dict:
    keys = [k for k in dict.fromkeys(keys) if k]
    return {t.key: t for t in site.get_many(keys)} if keys else {}


def build_pool(site) -> list[dict]:
    """Recent human edits to catalog records, one row per title, interleaved across editors, with titles, covers and names filled in."""
    since = (datetime.now(UTC) - timedelta(days=POOL_DAYS)).strftime("%Y-%m-%d")
    changes = [c for kind in POOL_KINDS for c in site.recentchanges({"kind": kind, "bot": False, "begin_date": since, "limit": POOL_PER_KIND})]
    changes = sorted((c for c in changes if record_key(c)), key=lambda c: int(c.id), reverse=True)
    records = fetch_things(site, [record_key(c) for c in changes])
    works = fetch_things(site, [ref_key(w) for t in records.values() for w in as_list(t.get("works"))[:1]])
    names = fetch_things(
        site,
        [ref_key(a) for t in records.values() for a in author_refs(t, works)] + [c.author.key for c in changes if c.author],
    )

    rows, seen = [], set()
    for c in changes:
        thing = records.get(record_key(c))
        if not thing or not (title := record_title(thing)) or title.casefold() in seen:
            continue
        seen.add(title.casefold())
        authors = [n for a in author_refs(thing, works) if (n := (names.get(ref_key(a)) or {}).get("name"))]
        editor = names.get(c.author.key) if c.author else None
        rows.append(
            build_row(
                id=str(c.id),
                key=thing.key,
                title=title,
                authors=", ".join(list(dict.fromkeys(authors))[:2]),
                cover_id=record_cover_id(thing),
                kind=c.kind,
                # Anonymous edits get "a visitor" when served, in the reader's language.
                editor=((editor or {}).get("displayname") or c.author.key.split("/")[-1]) if c.author else "",
                editor_key=c.author.key if c.author else "",
                comment="" if c.kind in DEFAULT_COMMENT_KINDS else clean_comment(c.comment),
            )
        )
        if len(rows) >= POOL_SIZE:
            break
    return interleave_by_editor(rows)


def interleave_by_editor(rows: list[dict]) -> list[dict]:
    """Round-robin the rows across editors so one busy librarian's run is spread through the pool instead of stacked.

    Editors keep their first-seen order and their own rows stay newest first; timestamps are restamped on the way out, so pool order is only about variety.
    """
    by_editor: dict[str, list[dict]] = {}
    for row in rows:
        by_editor.setdefault(row["editor_key"], []).append(row)
    queues = list(by_editor.values())
    return [row for turn in zip_longest(*queues) for row in turn if row is not None]
