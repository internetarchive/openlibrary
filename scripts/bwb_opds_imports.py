#!/usr/bin/env python3
"""
Daily incremental importer for Better World Books via OPDS 2.0 feed.

Replaces the monthly Better World Books CSV import (see
``partner_batch_imports.py``) with a JSON-feed crawl that filters
publications by ``metadata.modified`` relative to the previous run.

Two outputs are produced per run:

1. Import items written to the ``bwb-opds-YYYY-MM-DD`` batch (consumed by
   ``/api/import``). Records reuse the existing ``bwb:{isbn_13}`` source slug
   so the import API deduplicates against the monthly CSV pipeline rather
   than creating parallel edition records.
2. A JSONL sidecar of ``{isbn_13, price, currency, modified}`` rows used by
   the partial-update job that populates the Solr ``price`` field (see
   issue #12774, sub-task 2). The file is opened lazily — a run with zero
   fresh price rows leaves any prior snapshot untouched so the Solr updater
   never sees a half-empty handoff.

Open coordination items (tracked on issue #12774):

* Relationship to #11264's proposed Solr ``acquisitions`` array (overlaps
  with ``price`` + ``price_isbn``) — to be reconciled before sub-task 2.
* Runtime price lookup in ``openlibrary.core.vendors.get_betterworldbooks_metadata``
  vs. this batch-cached price path — both currently coexist.
* Sidecar path / retention policy is owner-configurable via ``--prices-out``;
  default lives under the OL data dir.

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
import time
from typing import Any

import requests
import web

try:
    import _init_path  # type: ignore[import-not-found]  # noqa: F401 side effect: add OL package root to sys.path
except ImportError:
    import scripts._init_path  # noqa: F401 same side effect when imported as a package

from infogami import config  # noqa: F401 side effects may be needed
from infogami.utils.delegate import create_site
from openlibrary.config import load_config
from openlibrary.core.acquisitions import Acquisition
from openlibrary.core.imports import Batch
from openlibrary.core.models import Edition
from openlibrary.core.tbp import FeedRegistry
from openlibrary.core.vendors import stage_bookworm_metadata
from openlibrary.plugins.upstream.utils import get_marc21_language
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.utils.isbn import to_isbn_13
from scripts.partner_batch_imports import is_low_quality_book, is_published_in_future_year
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.importer.bwb_opds")

OPDS_FEED_URL = "https://www.betterworldbooks.com/opds"
PROVIDER_NAME = "betterworldbooks"
ACQUISITION_REL = "http://opds-spec.org/acquisition/buy"
ISBN_URN_PREFIX = "urn:isbn:"
DEFAULT_STATE_FILE = "/openlibrary/data/bwb_opds_last_run.txt"
DEFAULT_PRICES_OUT = "/openlibrary/data/bwb_prices.jsonl"
EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)
REQUEST_TIMEOUT = 60
PAGE_SLEEP_SECONDS = 1.0


def read_state(path: str) -> datetime.datetime:
    """Return the last-run timestamp from ``path`` (UTC). Returns epoch if missing."""
    try:
        with open(path) as fh:
            raw = fh.read().strip()
    except FileNotFoundError:
        return EPOCH
    if not raw:
        return EPOCH
    return _parse_iso(raw)


def write_state(path: str, ts: datetime.datetime) -> None:
    """Atomically write ``ts`` (ISO 8601) to ``path``."""
    if parent := os.path.dirname(path):
        os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as fh:
        fh.write(ts.isoformat())
    os.replace(tmp, path)


def _parse_iso(value: str) -> datetime.datetime:
    """Parse an ISO 8601 timestamp, normalising to a tz-aware UTC datetime.

    BWB emits high-precision offsets like ``2026-05-19T14:47:58.5476301-04:00``
    which ``datetime.fromisoformat`` accepts on Python 3.11+.
    """
    dt = datetime.datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return dt.astimezone(datetime.UTC)


def extract_isbn(metadata: dict[str, Any]) -> str | None:
    """Return the ISBN-13 from an OPDS ``metadata.identifier`` URN, or None."""
    identifier = metadata.get("identifier") or ""
    if not identifier.startswith(ISBN_URN_PREFIX):
        return None
    return to_isbn_13(identifier[len(ISBN_URN_PREFIX) :])


def extract_price(publication: dict[str, Any]) -> dict[str, Any] | None:
    """Return ``{currency, value}`` from the first buy-acquisition link, or None."""
    for link in publication.get("links", []) or []:
        if link.get("rel") != ACQUISITION_REL:
            continue
        properties = link.get("properties") or {}
        price = properties.get("price") or {}
        if price.get("value") is not None and price.get("currency"):
            return {"currency": price["currency"], "value": price["value"]}
    return None


def extract_buy_url(publication: dict[str, Any]) -> str | None:
    """Return the href of the first buy-acquisition link, or None."""
    for link in publication.get("links", []) or []:
        if link.get("rel") == ACQUISITION_REL and link.get("href"):
            return link["href"]
    return None


def extract_acquisition(publication: dict[str, Any]) -> dict[str, Any] | None:
    """Return the acquisitions ``data`` blob for a publication, or None.

    Captures price + buy url from the OPDS buy link. Returns None when the
    publication has no buy acquisition at all (nothing to record).
    """
    price = extract_price(publication)
    url = extract_buy_url(publication)
    if not price and not url:
        return None
    data: dict[str, Any] = {"provider_name": PROVIDER_NAME}
    if price:
        data["price"] = price["value"]
        data["currency"] = price["currency"]
    if url:
        data["url"] = url
    return data


def extract_cover(publication: dict[str, Any]) -> str | None:
    for image in publication.get("images", []) or []:
        if image.get("rel") == "cover" and image.get("href"):
            return image["href"]
    return None


def _publication_id(publication: dict[str, Any]) -> str:
    """Return the publication's ``self`` link or raw identifier, for logging."""
    for link in publication.get("links", []) or []:
        if link.get("rel") == "self" and link.get("href"):
            return link["href"]
    return (publication.get("metadata") or {}).get("identifier") or "<unknown>"


def map_publication_to_olbook(publication: dict[str, Any]) -> dict[str, Any] | None:
    """Convert an OPDS publication to an OL import record.

    Returns None when the publication lacks ISBN-13, title, or authors —
    matching the spec sketch in issue #12774 which requires all three.
    """
    metadata = publication.get("metadata") or {}
    isbn_13 = extract_isbn(metadata)
    if not isbn_13:
        logger.warning("Skipping publication with no usable ISBN: %s", _publication_id(publication))
        return None

    title = metadata.get("title")
    authors = [{"name": a["name"]} for a in (metadata.get("author") or []) if a.get("name")]
    if not title or not authors:
        logger.warning("Skipping publication missing title/authors: %s", _publication_id(publication))
        return None

    languages = [marc for code in (metadata.get("language") or []) if code and (marc := get_marc21_language(code))]

    olbook: dict[str, Any] = {
        "title": title,
        "isbn_13": [isbn_13],
        "source_records": [f"bwb:{isbn_13}"],
        "authors": authors,
        "languages": languages,
        "publish_date": metadata.get("published", ""),
        "publishers": [],  # OPDS feed does not include publisher
    }
    if cover := extract_cover(publication):
        olbook["cover"] = cover
    return olbook


def find_next_url(feed: dict[str, Any]) -> str | None:
    for link in feed.get("links", []) or []:
        if link.get("rel") == "next" and link.get("href"):
            return link["href"]
    return None


def iter_pages(start_url: str, session: requests.Session, max_pages: int | None = None):
    """Yield successive OPDS feed pages, following ``rel=next`` links."""
    url: str | None = start_url
    seen: set[str] = set()
    page_num = 0
    while url:
        if url in seen:
            logger.warning("Cycle detected in OPDS pagination at %s; stopping.", url)
            return
        seen.add(url)
        page_num += 1
        if max_pages is not None and page_num > max_pages:
            logger.info("Reached --max-pages=%s; stopping pagination.", max_pages)
            return
        logger.info("Fetching OPDS page %d: %s", page_num, url)
        resp = session.get(url, timeout=REQUEST_TIMEOUT, headers={"Accept": "application/opds+json"})
        resp.raise_for_status()
        feed = resp.json()
        yield feed
        url = find_next_url(feed)
        if url:
            time.sleep(PAGE_SLEEP_SECONDS)


def process_feed(
    feed_url: str,
    since: datetime.datetime,
    prices_out_fh,
    max_pages: int | None = None,
    early_stop: bool = False,
    acquisitions_out: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], datetime.datetime]:
    """Crawl the OPDS feed and return (olbooks, max_modified_seen).

    Records are filtered to those with ``metadata.modified > since``. Price
    rows are written to ``prices_out_fh`` as they are encountered. The state
    cursor advances on every publication that is newer than ``since``, even
    when mapping fails — otherwise an unmappable but newer record would force
    every subsequent run to re-scan it forever.

    When ``acquisitions_out`` is supplied, an ``{"isbn_13", "data"}`` record
    is appended for each mapped publication that carries a buy acquisition, so
    the caller can upsert the ``acquisitions`` table once editions exist.

    Quality filters from ``partner_batch_imports`` (low-quality independently
    published reprints, future-dated publications) are applied so the OPDS
    pipeline excludes the same noise the monthly CSV importer does.

    ``early_stop`` (off by default): when enabled, pagination halts once a
    whole page contains zero records newer than ``since``. OPDS feeds are
    not guaranteed by spec to be sorted by ``modified``, so leave this off
    until BWB's ordering is confirmed empirically — otherwise an
    out-of-order stale page would cause the incremental run to miss fresh
    publications on later pages. Enable via ``--early-stop`` once verified.
    """
    session = requests.Session()
    olbooks: list[dict[str, Any]] = []
    max_modified = since

    for feed in iter_pages(feed_url, session, max_pages=max_pages):
        fresh_in_page = 0
        for publication in feed.get("publications", []) or []:
            metadata = publication.get("metadata") or {}
            modified_raw = metadata.get("modified")
            if not modified_raw:
                continue
            try:
                modified = _parse_iso(modified_raw)
            except ValueError:
                logger.warning("Skipping publication with unparsable modified=%r", modified_raw)
                continue
            if modified <= since:
                continue
            fresh_in_page += 1
            max_modified = max(max_modified, modified)

            olbook = map_publication_to_olbook(publication)
            if not olbook:
                continue
            if _should_exclude(olbook):
                continue
            olbooks.append(olbook)

            if price := extract_price(publication):
                prices_out_fh.write(
                    json.dumps(
                        {
                            "isbn_13": olbook["isbn_13"][0],
                            "price": price["value"],
                            "currency": price["currency"],
                        }
                    )
                    + "\n"
                )

            if acquisitions_out is not None and (acq := extract_acquisition(publication)):
                acquisitions_out.append({"isbn_13": olbook["isbn_13"][0], "data": acq})

        if early_stop and fresh_in_page == 0:
            logger.info("Page contains no records newer than %s; stopping (feed is modified-desc).", since.isoformat())
            break

    return olbooks, max_modified


def _should_exclude(olbook: dict[str, Any]) -> bool:
    """Apply partner-import quality filters to an OPDS-derived record."""
    # The CSV-path filters expect a ``title``; treat title-less records as
    # noise on the strict-quality path too.
    if not olbook.get("title"):
        return False
    try:
        if is_low_quality_book(olbook):
            return True
        if is_published_in_future_year(olbook):
            return True
    except (KeyError, ValueError, TypeError) as e:
        logger.warning("Quality filter failed for %s: %s", olbook.get("isbn_13"), e)
    return False


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

    Used so a run with zero fresh price rows does not clobber a prior
    snapshot that the Solr updater has not yet consumed.
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
    acquisitions_out: list[dict[str, Any]] | None = None,
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


def upsert_acquisitions(records: list[dict[str, Any]], provider_name: str = PROVIDER_NAME) -> int:
    """Upsert ``acquisitions`` rows for records whose edition already exists.

    Implements the post-batch edition mapping: an OPDS record's edition_id is
    unknown at submit time, so we resolve ``bwb:{isbn}`` to an existing OL
    edition by ISBN (no import side effects) and key the acquisition off its
    numeric work/edition ids. Records whose editions have not been imported
    yet are skipped — a later daily run picks them up once the import queue
    has processed them.

    Returns the number of rows upserted.
    """
    upserted = 0
    for record in records:
        isbn = record["isbn_13"]
        edition = Edition.from_isbn(isbn, allow_import=False)
        if not edition:
            continue
        works = edition.works
        if not works:
            logger.warning("Edition %s (isbn %s) has no work; skipping acquisition.", edition.key, isbn)
            continue
        edition_id = int(extract_numeric_id_from_olid(edition.key))
        work_id = int(extract_numeric_id_from_olid(works[0].key))
        Acquisition.upsert(work_id, edition_id, provider_name, data=record["data"])
        upserted += 1
    return upserted


def _registry_cursor(registry: FeedRegistry | None) -> datetime.datetime | None:
    """Return the registry's ``last_updated`` as a tz-aware UTC datetime, or None."""
    if registry is None or registry.get("last_updated") is None:
        return None
    last = registry.last_updated
    if isinstance(last, str):
        last = datetime.datetime.fromisoformat(last)
    return last.replace(tzinfo=datetime.UTC) if last.tzinfo is None else last.astimezone(datetime.UTC)


def main(
    ol_config: str,
    feed_url: str = OPDS_FEED_URL,
    provider_name: str = PROVIDER_NAME,
    state_file: str = DEFAULT_STATE_FILE,
    prices_out: str = DEFAULT_PRICES_OUT,
    since: str | None = None,
    max_pages: int | None = None,
    dry_run: bool = False,
    early_stop: bool = False,
) -> None:
    """Run one incremental BWB OPDS import.

    The incremental cutoff comes from the ``tbp_feed_registry`` row for this
    ``(provider_name, feed_url)`` (its ``last_updated`` cursor), falling back
    to the legacy ``state_file`` when the feed is not registered. After import,
    acquisitions are upserted for editions that already exist and the registry
    cursor is advanced.

    :param ol_config: Path to ``openlibrary.yml``.
    :param feed_url: OPDS 2.0 feed entry point.
    :param provider_name: Trusted-book-provider name; keys the registry row and acquisitions.
    :param state_file: Legacy cursor file, used only when the feed is not in the registry.
    :param prices_out: Path to JSONL price sidecar; opened lazily so a zero-row run leaves any
        prior snapshot intact (avoids handing the Solr updater an empty file mid-handoff).
    :param since: Optional ISO 8601 override for the incremental cutoff.
    :param max_pages: Safety cap on pagination depth (unbounded if None).
    :param dry_run: If True, print mapped records and do not touch the batch DB, registry, or state file.
    :param early_stop: Opt-in optimisation: stop pagination once a full page contains no records newer
        than the cutoff. OPDS spec does not mandate sort-by-modified, so leave disabled until
        BWB's feed order is empirically confirmed.
    """
    if not dry_run:
        load_config(ol_config)
        # Standalone cron has no request context; build the site so edition
        # lookups (Edition.from_isbn) work for the post-batch acquisition map.
        web.ctx.site = create_site()

    registry = None if dry_run else FeedRegistry.find(provider_name, feed_url)
    if since:
        cutoff = _parse_iso(since)
    else:
        cutoff = _registry_cursor(registry) or read_state(state_file)

    batch_name = f"bwb-opds-{datetime.datetime.now(datetime.UTC):%Y-%m-%d}"
    logger.info("Starting BWB OPDS import: cutoff=%s batch=%s", cutoff.isoformat(), batch_name)

    acquisitions: list[dict[str, Any]] = []
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

    upserted = upsert_acquisitions(acquisitions, provider_name)
    logger.info("Upserted %d acquisition rows (of %d candidates).", upserted, len(acquisitions))

    if max_modified > cutoff:
        # Strip tz: the registry/state store timezone-naive UTC.
        naive_max = max_modified.astimezone(datetime.UTC).replace(tzinfo=None)
        if registry is not None:
            FeedRegistry.advance(registry.id, last_updated=naive_max)
        write_state(state_file, max_modified)
        logger.info("Advanced cursor to %s.", max_modified.isoformat())
    else:
        logger.info("No newer publications since %s; leaving cursor untouched.", cutoff.isoformat())


if __name__ == "__main__":
    FnToCLI(main).run()
