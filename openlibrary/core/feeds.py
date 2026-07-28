"""Multi-feed harvest runner over the Trusted Book Provider feed registry.

Loops the registered feeds, harvests each under its per-feed lock via the
generic OPDS 2.0 adapter (:mod:`openlibrary.catalog.opds2`), stages new import
records to a batch, and advances the feed's cursor on success. The ``bookworm``
service (#12655) will drive :func:`harvest_all` on a cron; it also runs
standalone for dev and for the admin "harvest now" trigger.

Onboarding a new OPDS feed is therefore "register a row" — no bespoke script.
Per-feed quirks (import source-id prefix, ...) live in the registry ``data``
blob. Better World Books keeps its dedicated ``scripts/bwb_opds_imports.py``
for its quality filter + acquisition wiring; this runner covers the generic
case. See https://github.com/internetarchive/openlibrary/issues/12844.
"""

from __future__ import annotations

import datetime
import io
import logging
from typing import Any

from openlibrary.catalog import opds2
from openlibrary.catalog.opds2 import EPOCH, Source
from openlibrary.core.imports import Batch
from openlibrary.core.tbp import FeedRegistry

logger = logging.getLogger("openlibrary.feeds")


def source_for(feed: FeedRegistry) -> Source:
    """Build the generic OPDS Source for a registered feed.

    The import ``source_records`` prefix defaults to the provider name; a feed
    may override it via ``data.source_id_prefix``.
    """
    data = feed.data or {}
    return Source(
        provider_name=feed.provider_name,
        source_id_prefix=data.get("source_id_prefix") or feed.provider_name,
    )


def _since(feed: FeedRegistry) -> datetime.datetime:
    """The incremental cutoff for a feed: its cursor, or the epoch."""
    last_updated = feed.get("last_updated")
    if not last_updated:
        return EPOCH
    if isinstance(last_updated, str):
        return opds2.parse_iso(last_updated)
    if last_updated.tzinfo is None:
        return last_updated.replace(tzinfo=datetime.UTC)
    return last_updated.astimezone(datetime.UTC)


def _commit_batch(batch_name: str, olbooks: list[dict[str, Any]]) -> None:
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items([{"ia_id": b["source_records"][0], "data": b} for b in olbooks])


def harvest_feed(feed: FeedRegistry, *, ttl_seconds: int = 3600, max_pages: int | None = None) -> dict[str, Any]:
    """Harvest one registered feed under its per-feed lock.

    Crawls via the generic OPDS 2.0 adapter, stages new import records to a
    ``{provider}-opds-{date}`` batch, and advances the feed cursor on success.
    Skips without error (returns ``{"skipped": "locked"}``) if the feed is
    already being harvested. The cursor advances only after a successful crawl.
    """
    if not FeedRegistry.try_lock(feed.id, ttl_seconds=ttl_seconds):
        logger.info("feed %s is locked; skipping", feed.provider_name)
        return {"feed": feed.provider_name, "skipped": "locked"}
    try:
        since = _since(feed)
        olbooks, max_modified = opds2.process_feed(feed.url, since, io.StringIO(), source_for(feed), max_pages=max_pages)
        if olbooks:
            _commit_batch(f"{feed.provider_name}-opds-{max_modified:%Y-%m-%d}", olbooks)
        advanced = max_modified > since
        if advanced:
            FeedRegistry.advance(feed.id, last_updated=max_modified.replace(tzinfo=None))
        logger.info("harvested %s: %d records, advanced=%s", feed.provider_name, len(olbooks), advanced)
        return {"feed": feed.provider_name, "olbooks": len(olbooks), "advanced": advanced}
    finally:
        FeedRegistry.unlock(feed.id)


def harvest_all(*, ttl_seconds: int = 3600, max_pages: int | None = None) -> list[dict[str, Any]]:
    """Harvest every registered feed once. Entry point for the cron/runner."""
    return [harvest_feed(feed, ttl_seconds=ttl_seconds, max_pages=max_pages) for feed in FeedRegistry.all()]
