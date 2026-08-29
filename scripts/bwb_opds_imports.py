#!/usr/bin/env python
"""
Daily incremental importer for Better World Books via OPDS 2.0 feed.

Replaces the monthly Better World Books CSV import (see
``partner_batch_imports.py``) with a JSON-feed crawl that filters
publications by ``metadata.modified`` relative to the previous run.

Each run:

1. Crawls the OPDS feed for publications newer than the stored cursor.
2. Writes matched records to the ``bwb-opds-YYYY-MM-DD`` import batch
   (consumed by ``/api/import``). Records use the ``bwb:{isbn_13}`` source
   slug so the import API deduplicates against the monthly CSV pipeline.
3. Waits for the batch to finish processing, then upserts ``acquisitions``
   rows for editions that were successfully imported or already existed.
4. Advances the ``tbp_feed_registry`` cursor to the newest ``modified``
   timestamp seen.

Usage (on ``ol-home0`` cron container)::

    ./scripts/bwb_opds_imports.py /olsystem/etc/openlibrary.yml
"""

import datetime
import itertools
import logging
from collections.abc import Iterator
from typing import NotRequired, TypedDict, cast

import requests
import web
from pydantic import BaseModel

from openlibrary.core.acquisitions import Acquisition
from openlibrary.core.imports import Batch
from openlibrary.core.models import Edition
from openlibrary.core.tbp import FeedRegistry
from openlibrary.core.vendors import stage_bookworm_metadata
from openlibrary.plugins.upstream.utils import get_marc21_language
from openlibrary.setup import setup_for_script
from openlibrary.utils import extract_numeric_id_from_olid
from openlibrary.utils.isbn import to_isbn_13
from openlibrary.utils.opds_types import OPDSBuyLink, OPDSFeed, OPDSPublication
from scripts.partner_batch_imports import is_low_quality_book, is_published_in_future_year
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.importer.bwb_opds")

OPDS_FEED_URL = "https://www.betterworldbooks.com/opds"
PROVIDER_NAME = "betterworldbooks"
ISBN_URN_PREFIX = "urn:isbn:"
EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)


class OpenLibraryImportRecord(TypedDict):
    """
    TODO: Make this match (auto-get?) .openlibrary/schemata/import.schema.json
    and put in a centralized location.
    """

    title: str
    isbn_13: list[str]
    source_records: list[str]
    authors: list[dict[str, str]]
    languages: list[str]
    publish_date: str
    publishers: list[str]
    cover: NotRequired[str]


def _parse_iso(value: str) -> datetime.datetime:
    """Parse an ISO 8601 timestamp, normalising to a tz-aware UTC datetime.

    BWB emits high-precision offsets like ``2026-05-19T14:47:58.5476301-04:00``
    which ``datetime.fromisoformat`` accepts on Python 3.11+.
    """
    dt = datetime.datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return dt.astimezone(datetime.UTC)


def map_publication_to_ol_book(publication: OPDSPublication) -> OpenLibraryImportRecord | None:
    """Convert an OPDS publication to an OL import record.

    Returns None when the publication lacks ISBN-13, title, or authors —
    matching the spec sketch in issue #12774 which requires all three.
    """
    metadata = publication.metadata
    isbn_13: str | None = None
    identifier = metadata.identifier or ""
    if identifier.startswith(ISBN_URN_PREFIX):
        isbn_13 = to_isbn_13(identifier[len(ISBN_URN_PREFIX) :])

    if not isbn_13:
        logger.warning("Skipping publication with no usable ISBN: %s", publication.get_self_link())
        return None

    authors = [{"name": a.name} for a in metadata.author]
    if not metadata.title or not authors:
        logger.warning("Skipping publication missing title/authors: %s", publication.get_self_link())
        return None

    languages = [marc for code in metadata.language if (marc := get_marc21_language(code))]

    ol_book: OpenLibraryImportRecord = {
        "title": metadata.title,
        "isbn_13": [isbn_13],
        "source_records": [f"bwb:{isbn_13}"],
        "authors": authors,
        "languages": languages,
        "publish_date": metadata.published or "",
        "publishers": [],  # OPDS feed does not include publisher
    }
    if cover := publication.get_cover_url():
        ol_book["cover"] = cover
    return ol_book


class PublicationResult(BaseModel):
    provider_name: str
    local_publication_id: str
    ol_book: OpenLibraryImportRecord
    modified: datetime.datetime
    buy_link: OPDSBuyLink | None

    def get_prefixed_id(self) -> str:
        return f"{self.provider_name}:{self.local_publication_id}"


def process_feed(
    feed_url: str,
    since: datetime.datetime,
    max_pages: int | None = None,
) -> Iterator[PublicationResult]:
    """Yield a ``PublicationResult`` for each publication newer than ``since``.

    Publications without a self link, a ``modified`` timestamp, a usable
    ISBN-13, title, or authors are skipped. Quality filters from
    ``partner_batch_imports`` (low-quality reprints, future-dated publications)
    are also applied.
    """
    session = requests.Session()

    for feed in OPDSFeed.iter_pages(feed_url, session, max_pages=max_pages):
        for publication in feed.publications:
            pub_id = publication.get_self_link()
            if not pub_id:
                logger.warning("Skipping publication with no self link: %s", publication)
                continue

            modified = publication.get_modified_datetime()

            if modified is None:
                logger.warning("Skipping publication %s with no modified timestamp", pub_id)
                continue

            if modified <= since:
                continue

            ol_book = map_publication_to_ol_book(publication)
            if not ol_book:
                continue

            if _should_exclude(ol_book):
                logger.info("Skipping publication %s based on quality filters", pub_id)
                continue

            yield PublicationResult(provider_name="bwb", local_publication_id=pub_id, ol_book=ol_book, modified=modified, buy_link=publication.get_buy_link())


def _should_exclude(ol_book: OpenLibraryImportRecord) -> bool:
    """Apply partner-import quality filters to an OPDS-derived record."""
    try:
        return is_low_quality_book(ol_book) or is_published_in_future_year(ol_book)
    except (KeyError, ValueError, TypeError) as e:
        logger.warning("Quality filter failed for %s: %s", ol_book.get("isbn_13"), e)
    return False


def stage_incomplete_records_for_import(ol_books: list[OpenLibraryImportRecord]) -> None:
    """Mirror of ``partner_batch_imports.stage_incomplete_records_for_import``.

    For records lacking title/authors/publish_date, ask BookWorm to stage a
    richer record so ``/api/import`` can merge in extra metadata. See
    https://github.com/internetarchive/openlibrary/issues/9440.
    """
    required_fields = ("title", "authors", "publish_date")
    for book in ol_books:
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


def upsert_acquisitions(records: list[PublicationResult], edition_keys: list[str | None], provider_name: str, dry_run: bool = False) -> int:
    """Upsert ``acquisitions`` rows for each record in ``records``.

    :param edition_keys: A parallel list of OL edition keys (e.g.
    ``/books/OL123M``) produced by the import batch, one per record, or
    ``None`` when the import did not return a key. For ``None`` entries the
    edition is resolved by ISBN lookup instead. Records where no edition can
    be found are skipped.

    Returns the number of rows upserted.
    """
    upserted = 0
    for record, ol_key in zip(records, edition_keys):
        if not ol_key:
            isbn_13 = record.ol_book.get("isbn_13", [None])[0]
            edition = Edition.from_isbn(isbn_13, allow_import=False)
            if not edition:
                logger.warning("No existing edition for %s; skipping acquisition.", isbn_13)
                continue
        else:
            edition = cast(Edition | None, web.ctx.site.get(ol_key))
            if not edition:
                logger.warning("No existing edition for %s; skipping acquisition.", ol_key)
                continue

        works = edition.works
        if not works:
            logger.warning("%s Edition %s has no work; skipping acquisition.", record.local_publication_id, edition.key)
            continue
        edition_id = int(extract_numeric_id_from_olid(edition.key))
        work_id = int(extract_numeric_id_from_olid(works[0].key))
        if dry_run:
            logger.info(
                "Would upsert acquisition for work=%d edition=%d provider=%s local_publication_id=%s",
                work_id,
                edition_id,
                provider_name,
                record.local_publication_id,
            )
        else:
            Acquisition.upsert(
                work_id,
                edition_id,
                provider_name,
                record.local_publication_id,
                data=record.buy_link.model_dump() if record.buy_link else None,
            )
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


async def main(
    ol_config: str,
    feed_url: str = OPDS_FEED_URL,
    provider_name: str = PROVIDER_NAME,
    since: str | None = None,
    max_pages: int | None = None,
    dry_run: bool = False,
) -> None:
    """Run one incremental BWB OPDS import.

    The incremental cutoff comes from the ``tbp_feed_registry`` row for this
    ``(provider_name, feed_url)`` (its ``last_updated`` cursor), falling back
    to epoch when the feed is not yet registered. After import, acquisitions
    are upserted for editions that already exist and the registry cursor is
    advanced.

    :param ol_config: Path to ``openlibrary.yml``.
    :param feed_url: OPDS 2.0 feed entry point.
    :param provider_name: Trusted-book-provider name; keys the registry row and acquisitions.
    :param since: Optional ISO 8601 override for the incremental cutoff.
    :param max_pages: Safety cap on pagination depth (unbounded if None).
    :param dry_run: If True, print mapped records and do not touch the batch DB or registry.
    """
    setup_for_script(ol_config)

    registry = None if dry_run else FeedRegistry.find(provider_name, feed_url)
    if since:
        cutoff = _parse_iso(since)
    else:
        cutoff = _registry_cursor(registry) or EPOCH

    batch_name = f"bwb-opds-{datetime.datetime.now(datetime.UTC):%Y-%m-%d}"
    logger.info("Starting BWB OPDS import: cutoff=%s batch=%s", cutoff.isoformat(), batch_name)

    results: list[PublicationResult] = []
    for publication_result in process_feed(feed_url, cutoff, max_pages=max_pages):
        results.append(publication_result)
        if dry_run:
            print(publication_result.model_dump_json())

    max_modified = max((r.modified for r in results), default=cutoff)
    logger.info("Mapped %d new publications (max_modified=%s)", len(results), max_modified.isoformat())

    ol_keys: list[str | None] = [None] * len(results)
    ol_books = [r.ol_book for r in results]
    if not dry_run:
        # This likely needs to be awaited somehow...?
        stage_incomplete_records_for_import(ol_books)

        batch = Batch.find(batch_name) or Batch.new(batch_name)
        ia_ids = [f"bwb:{r.local_publication_id}" for r in results]
        items = [{"ia_id": ia_id, "data": r.ol_book} for ia_id, r in zip(ia_ids, results)]
        for chunk in itertools.batched(items, 1000, strict=False):
            batch.add_items(list(chunk))

        # Need the imports to finish being processed to ensure editions exist for
        # the acquisitions upsert step.
        import_items = await batch.poll_pending(ids=ia_ids, timeout=300)
        import_results = {i.ia_id: i for i in import_items}
        ol_keys = [import_results[f"bwb:{r.local_publication_id}"].ol_key for r in results]
    else:
        ol_keys = [None] * len(results)

    upserted = upsert_acquisitions(results, ol_keys, provider_name)
    logger.info("Upserted %d acquisition rows (of %d candidates).", upserted, len(results))

    if max_modified > cutoff:
        # Strip tz: the registry/state store timezone-naive UTC.
        naive_max = max_modified.astimezone(datetime.UTC).replace(tzinfo=None)
        if registry is not None:
            FeedRegistry.advance(registry.id, last_updated=naive_max)
        logger.info("Advanced cursor to %s.", max_modified.isoformat())
    else:
        logger.info("No newer publications since %s; leaving cursor untouched.", cutoff.isoformat())


if __name__ == "__main__":
    FnToCLI(main).run()
