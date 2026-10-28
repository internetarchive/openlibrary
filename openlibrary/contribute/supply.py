"""Which books need a hand: the most-read works with an edition missing a field, from Solr's edition child docs."""

import random
from collections.abc import Iterator
from dataclasses import dataclass

from openlibrary.contribute import pool
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.utils.dateutil import DAY_SECS, HOUR_SECS
from openlibrary.utils.request_context import site

# How many of the most-read works the list draws from; each load shows a random handful of them.
POOL_SIZE = 500
# The query scans every edition, so its picks are shared for an hour and only ever run on a background thread.
PICKS_KEY = "contribute.solr_picks"
PICKS_TTL = HOUR_SECS
# Stale picks are served for a week, so a quiet filter never makes a visitor wait on that query; rows are re-checked against the database anyway.
PICKS_KEEP = 7 * DAY_SECS

# The Solr edition field behind each record field. Page count is not indexed on editions, so it has no list of its own.
SOLR_FIELDS = {
    "covers": "cover_i",
    "languages": "language",
    "publishers": "publisher",
    "lccn": "lccn",
    "oclc_numbers": "oclc",
}
# Where missing means more than an empty Solr field. A scanned book shows its first page as the cover.
MISSING_CLAUSES = {"covers": "(*:* -cover_i:* -ia:*)"}


@dataclass(frozen=True)
class Candidate:
    edition: object
    readers: int | None = None


def missing_query(fields: tuple[str, ...]) -> str:
    """Editions with an ISBN (so the link-outs work) missing any of ``fields``."""
    missing = " OR ".join(MISSING_CLAUSES.get(f, f"(*:* -{SOLR_FIELDS[f]}:*)") for f in fields if f in SOLR_FIELDS)
    return f"type:edition AND isbn:* AND ({missing})"


class PartialResults(Exception):
    """Solr ran out of time and returned only some matches; never cache those."""


# Uncapped, so the background refill finishes instead of returning whatever Solr found in 10s.
FILL_TIMEOUT_SECONDS = 120
# Outlasts the query, so a second rebuild can't start while the first still runs.
PICKS_LOCK_TTL = FILL_TIMEOUT_SECONDS + 60


def _solr_picks(fields: list[str], limit: int) -> list[list]:
    """``[edition key, readers]`` for the most-read works with an edition missing one of ``fields``."""
    edition_q = missing_query(tuple(fields))
    result = get_solr().select(
        "{!parent which=type:work v=$edq}",
        fields=["key", "readinglog_count", "editions:[subquery]"],
        rows=limit,
        sort="readinglog_count desc",
        edq=edition_q,
        editions_q="{!terms f=_root_ v=$row.key}",
        editions_fq=edition_q,
        editions_fl="key",
        editions_rows=1,
        _timeout=FILL_TIMEOUT_SECONDS,
        _pass_time_allowed=False,
        request_label="CONTRIBUTE_TASKS",
    )
    if result.partial:
        raise PartialResults(edition_q)
    return [[d["editions"]["docs"][0]["key"], d.get("readinglog_count")] for d in result.docs if d.get("editions", {}).get("docs")]


def cached_picks(fields: tuple[str, ...], limit: int) -> list[list] | None:
    """The shared picks for ``fields``, or None while a cold cache fills in the background."""
    wanted = sorted(f for f in fields if f in SOLR_FIELDS)
    return pool.get(f"{PICKS_KEY}:{','.join(wanted)}:{limit}", PICKS_TTL, lambda: _solr_picks(wanted, limit), lock_ttl=PICKS_LOCK_TTL, keep=PICKS_KEEP)


def solr_candidates(fields: tuple[str, ...], limit: int = POOL_SIZE, batch: int = 50) -> Iterator[Candidate] | None:
    """The most-read works with an edition missing one of ``fields``, one edition per work, in random order.

    None while the picks are still being built. Editions load a batch at a time, so a caller that stops early never fetches the whole pool.
    """
    if not any(f in SOLR_FIELDS for f in fields):
        return iter(())
    if (picks := cached_picks(fields, limit)) is None:
        return None
    return _load(picks, batch)


def _load(picks: list[list], batch: int) -> Iterator[Candidate]:
    picks = random.sample(picks, len(picks))
    for i in range(0, len(picks), batch):
        chunk = picks[i : i + batch]
        editions = {e.key: e for e in site.get().get_many([key for key, _readers in chunk])}
        yield from (Candidate(editions[key], readers) for key, readers in chunk if key in editions)
