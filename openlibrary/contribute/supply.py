"""Which books need a hand: the most-read works with an edition missing a field, from Solr's edition child docs."""

import logging
from dataclasses import dataclass

import httpx
import web

from openlibrary.core import cache
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.utils.dateutil import HOUR_SECS

logger = logging.getLogger("openlibrary.contribute")

# The Solr edition field behind each record field. Page count is not indexed on editions, so it has no list of its own.
SOLR_FIELDS = {
    "languages": "language",
    "publishers": "publisher",
    "lccn": "lccn",
    "oclc_numbers": "oclc",
}


@dataclass(frozen=True)
class Candidate:
    edition: object
    readers: int | None = None


def missing_query(fields: tuple[str, ...]) -> str:
    """Editions with an ISBN (so the link-outs work) missing any of ``fields``."""
    missing = " OR ".join(f"(*:* -{SOLR_FIELDS[f]}:*)" for f in fields if f in SOLR_FIELDS)
    return f"type:edition AND isbn:* AND ({missing})"


class PartialResults(Exception):
    """Solr ran out of time and returned only some matches; never cache those."""


# Uncapped, so the background refill finishes instead of returning whatever Solr found in 10s.
FILL_TIMEOUT_SECONDS = 120


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
    )
    if result.partial:
        raise PartialResults(edition_q)
    return [[d["editions"]["docs"][0]["key"], d.get("readinglog_count")] for d in result.docs if d.get("editions", {}).get("docs")]


# The query scans every edition, so it is shared for an hour; stale entries refill in the background.
_cached_picks = cache.memcache_memoize(_solr_picks, key_prefix="contribute.solr_picks", timeout=HOUR_SECS)


def solr_candidates(fields: tuple[str, ...], limit: int = 200) -> list[Candidate]:
    """The most-read works with an edition missing one of ``fields``, one edition per work."""
    if not any(f in SOLR_FIELDS for f in fields):
        return []
    try:
        picks = _cached_picks(sorted(fields), limit)
    except PartialResults, httpx.HTTPError:
        logger.exception("contribute: Solr candidates failed for %s", fields)
        return []
    editions = {e.key: e for e in web.ctx.site.get_many([key for key, _readers in picks])}
    return [Candidate(editions[key], readers) for key, readers in picks if key in editions]
