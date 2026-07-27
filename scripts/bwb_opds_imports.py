#!/usr/bin/env python3
"""
Daily incremental importer for Better World Books via OPDS 2.0 feed.

Better World Books is the first consumer of the generic OPDS 2.0 adapter in
``openlibrary.catalog.opds2``. This module supplies only the BWB-specific
``Source`` config (import source-id prefix + quality filter) and the
orchestration around a run: batch staging, acquisition upserts, and the
FeedRegistry incremental cursor. Onboarding another OPDS feed should not need a
new script — register it and reuse the adapter.

Two outputs are produced per run:

1. Import items written to the ``bwb-opds-YYYY-MM-DD`` batch (consumed by
   ``/api/import``). Records reuse the existing ``bwb:{isbn_13}`` source slug
   so the import API deduplicates against the monthly CSV pipeline rather than
   creating parallel edition records.
2. A JSONL sidecar of ``{isbn_13, price, currency}`` rows used by the
   partial-update job that populates the Solr ``price`` field. The file is
   opened lazily so a run with zero fresh price rows leaves any prior snapshot
   untouched.

Usage (on ``ol-home0`` cron container)::

    PYTHONPATH=/openlibrary python3 /openlibrary/scripts/bwb_opds_imports.py \\
        /olsystem/etc/openlibrary.yml
"""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import logging
import os
from typing import Any

import requests
import web

try:
    import _init_path  # type: ignore[import-not-found]  # noqa: F401 side effect: add OL package root to sys.path
except ImportError:
    import scripts._init_path  # noqa: F401 same side effect when imported as a package

from infogami import config  # noqa: F401 side effects may be needed
from openlibrary.catalog import opds2
from openlibrary.catalog.opds2 import EPOCH, ISBN_URN_PREFIX, Source, build_acquisition_data, parse_iso
from openlibrary.config import load_config
from openlibrary.core.acquisitions import Acquisition
from openlibrary.core.imports import Batch
from openlibrary.core.tbp import FeedRegistry
from openlibrary.core.vendors import stage_bookworm_metadata
from openlibrary.utils import extract_numeric_id_from_olid
from scripts.partner_batch_imports import is_low_quality_book, is_published_in_future_year
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.importer.bwb_opds")

OPDS_FEED_URL = "https://www.betterworldbooks.com/opds"
BWB_PROVIDER_NAME = "betterworldbooks"
DEFAULT_STATE_FILE = "/openlibrary/data/bwb_opds_last_run.txt"
DEFAULT_PRICES_OUT = "/openlibrary/data/bwb_prices.jsonl"


def _bwb_record_filter(olbook: dict[str, Any]) -> bool:
    """BWB quality filter: drop low-quality reprints / future-dated books, so the
    OPDS pipeline excludes the same noise the monthly CSV importer does."""
    return is_low_quality_book(olbook) or is_published_in_future_year(olbook)


# BWB's specialization of the generic OPDS 2.0 adapter. Per-feed quirks live
# here (centrally), not in a forked script.
BWB_SOURCE = Source(
    provider_name=BWB_PROVIDER_NAME,
    source_id_prefix="bwb",
    record_filter=_bwb_record_filter,
)


def map_publication_to_olbook(publication: dict[str, Any]) -> dict[str, Any] | None:
    """BWB-bound convenience wrapper over :func:`opds2.map_publication_to_olbook`."""
    return opds2.map_publication_to_olbook(publication, BWB_SOURCE)


def process_feed(
    feed_url: str,
    since: datetime.datetime,
    prices_out_fh,
    max_pages: int | None = None,
    early_stop: bool = False,
    acquisitions_out: list[tuple[str, dict[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], datetime.datetime]:
    """BWB-bound convenience wrapper over :func:`opds2.process_feed`."""
    return opds2.process_feed(
        feed_url,
        since,
        prices_out_fh,
        BWB_SOURCE,
        max_pages=max_pages,
        early_stop=early_stop,
        acquisitions_out=acquisitions_out,
    )


def read_state(path: str) -> datetime.datetime:
    """Return the last-run timestamp from ``path`` (UTC). Returns epoch if missing."""
    try:
        with open(path) as fh:
            raw = fh.read().strip()
    except FileNotFoundError:
        return EPOCH
    if not raw:
        return EPOCH
    return parse_iso(raw)


def write_state(path: str, ts: datetime.datetime) -> None:
    """Atomically write ``ts`` (ISO 8601) to ``path``."""
    if parent := os.path.dirname(path):
        os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as fh:
        fh.write(ts.isoformat())
    os.replace(tmp, path)


def _coerce_utc(value: datetime.datetime | str) -> datetime.datetime:
    """Normalise a DB timestamp (naive UTC, or an sqlite string) to aware UTC."""
    if isinstance(value, str):
        return parse_iso(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC)
    return value.astimezone(datetime.UTC)


def resolve_cutoff(
    feed_url: str,
    since: str | None,
    state_file: str,
    provider_name: str = BWB_PROVIDER_NAME,
) -> datetime.datetime:
    """Return the incremental cutoff for this run.

    Precedence: an explicit ``--since`` override > the FeedRegistry cursor (the
    source of truth once the feed is registered) > the file-state fallback >
    the epoch. The file-state remains only as a fallback for feeds not yet in
    the registry (#12844).
    """
    if since:
        return parse_iso(since)
    feed = FeedRegistry.find(provider_name, feed_url)
    if feed and feed.get("last_updated"):
        return _coerce_utc(feed.last_updated)
    return read_state(state_file)


def advance_cursor(
    feed_url: str,
    max_modified: datetime.datetime,
    state_file: str,
    provider_name: str = BWB_PROVIDER_NAME,
) -> None:
    """Persist ingestion progress.

    Advances the FeedRegistry cursor (source of truth) when the feed is
    registered, and always updates the file-state fallback.
    """
    if feed := FeedRegistry.find(provider_name, feed_url):
        FeedRegistry.advance(feed.id, last_updated=max_modified.replace(tzinfo=None))
    write_state(state_file, max_modified)


def upsert_acquisition(
    work_id: int,
    edition_id: int,
    isbn_13: str,
    publication: dict[str, Any],
) -> Acquisition | None:
    """Upsert the BWB acquisition row for an already-resolved (work, edition).

    Idempotent on the ``(local_id, provider_name)`` unique constraint, so
    re-running the feed refreshes price/format metadata rather than creating
    duplicate rows. ``local_id`` is the ISBN URN, matching the OPDS
    ``metadata.identifier``.
    """
    return Acquisition.upsert(
        work_id=work_id,
        edition_id=edition_id,
        provider_name=BWB_PROVIDER_NAME,
        local_id=f"{ISBN_URN_PREFIX}{isbn_13}",
        data=build_acquisition_data(publication),
    )


def resolve_edition_ids(isbn_13: str) -> tuple[int, int] | None:
    """Resolve an ISBN-13 to ``(work_id, edition_id)`` integers for an edition
    ALREADY in the catalog, or None.

    Existing editions only — no import/Amazon side effects. This is option (a)
    from #12844: acquisitions attach at ingestion time for ISBNs that already
    resolve; editions created later by the import get their acquisition linked
    by :func:`link_acquisition_for_edition` (the post-import hook). Ids are the
    numeric OLID parts, matching the convention used by checkins/bookshelves.
    """
    matches = web.ctx.site.things({"type": "/type/edition", "isbn_13": isbn_13})
    if not matches:
        return None
    edition = web.ctx.site.get(matches[0])
    if not edition or not edition.works:
        return None
    work_id = int(extract_numeric_id_from_olid(edition.works[0].key))
    edition_id = int(extract_numeric_id_from_olid(edition.key))
    return work_id, edition_id


def stage_acquisitions(acquisitions: list[tuple[str, dict[str, Any]]]) -> int:
    """Upsert acquisition rows for feed records whose ISBN resolves to an
    existing edition. Returns the number upserted. Unresolved ISBNs are left
    for the post-import hook once their edition is created.
    """
    upserted = 0
    for isbn_13, data in acquisitions:
        if not (ids := resolve_edition_ids(isbn_13)):
            continue
        work_id, edition_id = ids
        Acquisition.upsert(
            work_id=work_id,
            edition_id=edition_id,
            provider_name=BWB_PROVIDER_NAME,
            local_id=f"{ISBN_URN_PREFIX}{isbn_13}",
            data=data,
        )
        upserted += 1
    return upserted


def link_acquisition_for_edition(edition_key: str, publication: dict[str, Any]) -> Acquisition | None:
    """Post-import hook: link a BWB acquisition to a newly-created edition.

    Called once the import pipeline has created the edition for a ``bwb:{isbn}``
    source record (option (a) from #12844 — the deferred half of
    :func:`stage_acquisitions`).
    """
    edition = web.ctx.site.get(edition_key)
    if not edition or not edition.works:
        return None
    isbn_13 = (edition.isbn_13 or [None])[0]
    if not isbn_13:
        return None
    return upsert_acquisition(
        work_id=int(extract_numeric_id_from_olid(edition.works[0].key)),
        edition_id=int(extract_numeric_id_from_olid(edition.key)),
        isbn_13=isbn_13,
        publication=publication,
    )


def stage_incomplete_records_for_import(olbooks: list[dict[str, Any]]) -> None:
    """Mirror of ``promise_batch_imports.stage_incomplete_records_for_import``.

    For records lacking title/authors/publish_date, ask BookWorm to stage a
    richer record so ``/api/import`` can merge in extra metadata. See
    https://github.com/internetarchive/openlibrary/issues/9440.
    """
    required_fields = ("title", "authors", "publish_date")
    for book in olbooks:
        if all(book.get(field) for field in required_fields):
            continue
        isbn_list = book.get("isbn_13") or []
        isbn = isbn_list[0] if isbn_list else None
        if not isbn:
            continue
        try:
            stage_bookworm_metadata(identifier=isbn)
        except requests.exceptions.ConnectionError:
            logger.exception("Affiliate Server unreachable")
            continue


class _LazyWriter:
    """File-like wrapper that opens ``path`` only on the first ``write``.

    Used so a run with zero fresh price rows does not clobber a prior snapshot
    that the Solr updater has not yet consumed.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._fh: Any = None

    def write(self, data: str) -> int:
        if self._fh is None:
            if parent := os.path.dirname(self._path):
                os.makedirs(parent, exist_ok=True)
            self._fh = open(self._path, "w")  # noqa: SIM115 lifetime managed by close()
        return self._fh.write(data)

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()


def _run_feed(
    feed_url: str,
    cutoff: datetime.datetime,
    prices_out: str,
    max_pages: int | None,
    dry_run: bool,
    early_stop: bool = False,
    acquisitions_out: list[tuple[str, dict[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], datetime.datetime]:
    """Process the OPDS feed, routing price rows to disk or to a discard buffer."""
    if dry_run:
        with contextlib.nullcontext(io.StringIO()) as prices_fh:
            return process_feed(feed_url, cutoff, prices_fh, max_pages=max_pages, early_stop=early_stop, acquisitions_out=acquisitions_out)
    writer = _LazyWriter(prices_out)
    try:
        return process_feed(feed_url, cutoff, writer, max_pages=max_pages, early_stop=early_stop, acquisitions_out=acquisitions_out)
    finally:
        writer.close()


def commit_batch(batch_name: str, olbooks: list[dict[str, Any]], batch_size: int = 1000) -> None:
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    items = [{"ia_id": b["source_records"][0], "data": b} for b in olbooks]
    for i in range(0, len(items), batch_size):
        batch.add_items(items[i : i + batch_size])


def main(
    ol_config: str,
    feed_url: str = OPDS_FEED_URL,
    state_file: str = DEFAULT_STATE_FILE,
    prices_out: str = DEFAULT_PRICES_OUT,
    since: str | None = None,
    max_pages: int | None = None,
    dry_run: bool = False,
    early_stop: bool = False,
) -> None:
    """Run one incremental BWB OPDS import.

    :param ol_config: Path to ``openlibrary.yml``.
    :param feed_url: OPDS 2.0 feed entry point.
    :param state_file: Path to file storing last successful run's max ``modified`` ts.
    :param prices_out: Path to JSONL price sidecar; opened lazily so a zero-row run leaves any
        prior snapshot intact (avoids handing the Solr updater an empty file mid-handoff).
    :param since: Optional ISO 8601 override for the incremental cutoff.
    :param max_pages: Safety cap on pagination depth (unbounded if None).
    :param dry_run: If True, print mapped records and do not touch the batch DB or state file.
    :param early_stop: Opt-in optimisation: stop pagination once a full page contains no records newer
        than the cutoff. OPDS spec does not mandate sort-by-modified, so leave disabled until
        BWB's feed order is empirically confirmed.
    """
    batch_name = f"bwb-opds-{datetime.datetime.now(datetime.UTC):%Y-%m-%d}"

    if dry_run:
        # Don't touch the DB in dry-run: file-state (or --since) only.
        cutoff = parse_iso(since) if since else read_state(state_file)
    else:
        load_config(ol_config)
        cutoff = resolve_cutoff(feed_url, since, state_file)

    logger.info("Starting BWB OPDS import: cutoff=%s batch=%s", cutoff.isoformat(), batch_name)

    acquisitions: list[tuple[str, dict[str, Any]]] = []
    olbooks, max_modified = _run_feed(
        feed_url=feed_url,
        cutoff=cutoff,
        prices_out=prices_out,
        max_pages=max_pages,
        dry_run=dry_run,
        early_stop=early_stop,
        acquisitions_out=acquisitions,
    )

    logger.info("Mapped %d new publications (max_modified=%s)", len(olbooks), max_modified.isoformat())

    if dry_run:
        for book in olbooks:
            print(json.dumps(book), flush=True)
        return

    if olbooks:
        stage_incomplete_records_for_import(olbooks)
        commit_batch(batch_name, olbooks)

    if acquisitions:
        # Option (a): attach acquisitions for ISBNs that already resolve to an
        # existing edition; the rest are linked post-import once created.
        linked = stage_acquisitions(acquisitions)
        logger.info("Upserted %d/%d acquisitions for already-resolved editions", linked, len(acquisitions))

    if max_modified > cutoff:
        advance_cursor(feed_url, max_modified, state_file)
        logger.info("Advanced cursor to %s (registry + file-state)", max_modified.isoformat())
    else:
        logger.info("No newer publications since %s; leaving cursor untouched.", cutoff.isoformat())


if __name__ == "__main__":
    FnToCLI(main).run()
