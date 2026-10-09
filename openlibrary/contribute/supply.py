"""Which books need a hand: the most-read works with an edition missing a field, from Solr's edition child docs."""

from dataclasses import dataclass

import web

from openlibrary.plugins.worksearch.search import get_solr

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


def solr_candidates(fields: tuple[str, ...], limit: int = 50) -> list[Candidate]:
    """The most-read works with an edition missing one of ``fields``, one edition per work."""
    if not any(f in SOLR_FIELDS for f in fields):
        return []
    edition_q = missing_query(fields)
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
    )
    picks = [(d["editions"]["docs"][0]["key"], d.get("readinglog_count")) for d in result.docs if d.get("editions", {}).get("docs")]
    editions = {e.key: e for e in web.ctx.site.get_many([key for key, _readers in picks])}
    return [Candidate(editions[key], readers) for key, readers in picks if key in editions]


def missing_count(fields: tuple[str, ...]) -> int:
    """How many works have an edition missing one of ``fields``. The rail's count."""
    if not any(f in SOLR_FIELDS for f in fields):
        return 0
    return get_solr().select("{!parent which=type:work v=$edq}", rows=0, edq=missing_query(fields)).num_found
