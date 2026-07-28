"""BookWorm feed-ingestion runner (#12655 / #12844).

Composes the staging pipeline that the ``bookworm`` service runs on a cron
(and that also runs standalone on dev):

1. :func:`stage_feed` harvests a registered feed into the ``tbp_staged_record``
   buffer (records + acquisition metadata), under the feed's lock, advancing the
   cursor on success.
2. :func:`promote_pending` drains staged records into the import queue.
3. :func:`run_once` does both for every registered feed — one cron tick.

The staged buffer sits in the isolated staging DB, so bulk harvesting never
contends with production Open Library. ``manage-imports`` drains the resulting
import queue (dual-source: this queue + the legacy main-schema one).
"""

from __future__ import annotations

import io
import logging
from typing import Any

from openlibrary.catalog import opds2
from openlibrary.core import feeds
from openlibrary.core.imports import Batch
from openlibrary.core.staged import PROMOTED, StagedRecord
from openlibrary.core.tbp import FeedRegistry

logger = logging.getLogger("openlibrary.bookworm")


def stage_feed(feed: FeedRegistry, *, max_pages: int | None = None) -> dict[str, Any]:
    """Harvest one feed into the staged_record buffer, under its per-feed lock.

    Records and their acquisition metadata land in staging (not yet the import
    queue); the cursor advances on success. Idempotent: re-harvesting refreshes
    staged rows rather than duplicating them.
    """
    if not FeedRegistry.try_lock(feed.id):
        logger.info("feed %s is locked; skipping", feed.provider_name)
        return {"feed": feed.provider_name, "skipped": "locked"}
    try:
        since = feeds._since(feed)
        acquisitions: list[tuple[str, dict]] = []
        olbooks, max_modified = opds2.process_feed(feed.url, since, io.StringIO(), feeds.source_for(feed), max_pages=max_pages, acquisitions_out=acquisitions)
        acq_by_isbn = dict(acquisitions)
        for olbook in olbooks:
            isbn_13 = olbook["isbn_13"][0]
            StagedRecord.upsert(
                feed.provider_name,
                f"urn:isbn:{isbn_13}",
                olbook,
                acquisition=acq_by_isbn.get(isbn_13),
            )
        advanced = max_modified > since
        if advanced:
            FeedRegistry.advance(feed.id, last_updated=max_modified.replace(tzinfo=None))
        logger.info("staged %s: %d records, advanced=%s", feed.provider_name, len(olbooks), advanced)
        return {"feed": feed.provider_name, "staged": len(olbooks), "advanced": advanced}
    finally:
        FeedRegistry.unlock(feed.id)


def promote_pending(limit: int = 1000) -> int:
    """Promote staged records into the import queue. Returns the number promoted.

    Groups by provider into ``{provider}-staged`` batches; the import batch
    dedupes on ``ia_id`` so promotion is idempotent. Promoted rows are marked so
    they drop out of the queue.
    """
    pending = StagedRecord.pending(limit=limit)
    if not pending:
        return 0
    by_provider: dict[str, list[StagedRecord]] = {}
    for rec in pending:
        by_provider.setdefault(rec.provider_name, []).append(rec)
    promoted = 0
    for provider, recs in by_provider.items():
        batch = Batch.find(f"{provider}-staged") or Batch.new(f"{provider}-staged")
        batch.add_items([{"ia_id": r.record["source_records"][0], "data": r.record} for r in recs])
        for rec in recs:
            StagedRecord.set_status(rec.id, PROMOTED)
            promoted += 1
    logger.info("promoted %d staged records", promoted)
    return promoted


def run_once(*, max_pages: int | None = None) -> dict[str, Any]:
    """One bookworm cycle: harvest every feed into staging, then promote."""
    staged = [stage_feed(feed, max_pages=max_pages) for feed in FeedRegistry.all()]
    promoted = promote_pending()
    return {"staged": staged, "promoted": promoted}
