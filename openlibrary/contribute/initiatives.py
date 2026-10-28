"""An initiative: a fixed list of editions that Tasks works through.

The list is picked once and frozen in the store, so progress means gaps filled, not a pool that drifts as books get fixed.
Nothing builds it by hand: the first request after a deploy starts the pick on a background thread, as ``pool`` does.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from infogami.utils.delegate import create_site
from openlibrary.contribute import pool, tasks
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.utils.dateutil import DAY_SECS, MINUTE_SECS

logger = logging.getLogger("openlibrary.contribute.initiatives")

# This many people saying "I couldn't find it" takes a gap off the list: one could just be in a hurry.
NOT_FOUND_PEOPLE = 2
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
    # ``size`` -> ``[[edition key, readers], ...]``, most-read first.
    pick: Callable[[int], list[list]]

    @property
    def store_key(self) -> str:
        return f"contribute-initiative-{self.slug}"


def pick_most_read(size: int) -> list[list]:
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


# The one Tasks works through. A new initiative is a new slug: the old list stays in the store for comparison.
ACTIVE = Initiative("most-read-2026-11", 2000, pick_most_read)


def load_or_freeze(initiative: Initiative, site) -> list[list]:
    """The frozen list from the store; the first call picks it and stores it."""
    if doc := site.store.get(initiative.store_key):
        return doc["editions"]
    editions = initiative.pick(initiative.size)
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
        if len(doc.get("people", [])) >= NOT_FOUND_PEOPLE:
            found.setdefault(doc["edition"], set()).add(doc["field"])
    return found


def build_gaps(initiative: Initiative, site, batch: int = 100) -> list[list]:
    """Every edition on the list as ``[key, readers, open fields, fields nobody could find]``, read from the database."""
    picks = load_or_freeze(initiative, site)
    unfindable = not_found_fields(site)
    rows = []
    for i in range(0, len(picks), batch):
        chunk = picks[i : i + batch]
        editions = {e.key: e for e in site.get_many([key for key, _readers in chunk])}
        for key, readers in chunk:
            # A merged or deleted edition has nothing left to fill.
            if not (edition := editions.get(key)) or edition.type.key != "/type/edition":
                continue
            missing = [t.field for t in tasks.tasks_for_edition(edition)]
            skipped = unfindable.get(key, set())
            rows.append([key, readers, [f for f in missing if f not in skipped], [f for f in missing if f in skipped]])
    return rows


def get_gaps(initiative: Initiative = ACTIVE) -> list[list] | None:
    """The shared gaps for ``initiative``, or None while the first build (and on a new initiative, the pick) runs."""
    # A fresh anonymous site for the thread: the request's carries the visitor's auth token and its own cache.
    return pool.get(f"contribute.initiative:{initiative.slug}", OPEN_TTL, lambda: build_gaps(initiative, create_site()), lock_ttl=OPEN_LOCK_TTL, keep=DAY_SECS)


def progress(gaps: list[list]) -> dict[str, int]:
    """How far the initiative has come: editions with nothing left to fill, out of all of them, and the gaps still open."""
    return {
        "done": sum(1 for _key, _readers, open_fields, _skipped in gaps if not open_fields),
        "total": len(gaps),
        "open": sum(len(open_fields) for _key, _readers, open_fields, _skipped in gaps),
        "not_found": sum(len(skipped) for _key, _readers, _open, skipped in gaps),
    }


def record_not_found(site, edition_key: str, fld: str, user_key: str) -> None:
    """Note that ``user_key`` looked for ``fld`` on the edition and couldn't find it. Kept apart from the record, so it isn't an edit."""
    key = f"{NOT_FOUND_TYPE}-{edition_key.rsplit('/', maxsplit=1)[-1]}-{fld}"
    doc = site.store.get(key) or {"type": NOT_FOUND_TYPE, "edition": edition_key, "field": fld, "people": []}
    if user_key not in doc["people"]:
        doc["people"] = [*doc["people"], user_key]
        site.store[key] = doc
