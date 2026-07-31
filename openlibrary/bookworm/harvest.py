"""BookWorm feed harvesting (#12844).

Fetch a registered feed, parse its publications into Open Library import records
(carrying ``acquisitions[]``), and submit them to OL's existing ``import_item``
queue via :class:`~openlibrary.core.imports.Batch`. ImportBot (manage-imports)
then loads them, and the catalog writes the acquisitions.

Per-feed cursor styles (from the registry ``data`` blob):

- ``client`` (BWB, Lenny): crawl ``rel=next``; when publications carry a
  ``modified`` timestamp, keep only those newer than the cursor and advance to
  the newest seen.
- ``modified_since`` (Gutenberg): inject ``modified_since=<cursor date>`` into
  the request so the server returns only changed items; advance the cursor to
  the run time.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from openlibrary.bookworm import opds
from openlibrary.bookworm.registry import CURSOR_MODIFIED_SINCE, FeedRegistry
from openlibrary.core.imports import Batch

logger = logging.getLogger("openlibrary.bookworm.harvest")

REQUEST_TIMEOUT = 60
EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)


def _as_utc(value: datetime.datetime | str | None) -> datetime.datetime | None:
    if not value:
        return None
    dt = datetime.datetime.fromisoformat(value) if isinstance(value, str) else value
    return dt.replace(tzinfo=datetime.UTC) if dt.tzinfo is None else dt.astimezone(datetime.UTC)


def request_url(feed: FeedRegistry, since: datetime.datetime) -> str:
    """The URL to fetch: for ``modified_since`` feeds, inject the cursor date."""
    if feed.cursor_style != CURSOR_MODIFIED_SINCE:
        return feed.url
    parts = urlparse(feed.url)
    query = parse_qs(parts.query)
    query["modified_since"] = [since.date().isoformat()]
    return urlunparse(parts._replace(query=urlencode(query, doseq=True)))


def iter_pages(start_url: str, session: requests.Session, max_pages: int | None = None):
    """Yield OPDS pages, following ``rel=next``."""
    url: str | None = start_url
    seen: set[str] = set()
    page_num = 0
    while url:
        if url in seen:
            return
        seen.add(url)
        page_num += 1
        if max_pages is not None and page_num > max_pages:
            return
        resp = session.get(url, timeout=REQUEST_TIMEOUT, headers={"Accept": "application/opds+json"})
        resp.raise_for_status()
        page = resp.json()
        yield page
        url = next(
            (link["href"] for link in (page.get("links") or []) if link.get("rel") == "next" and link.get("href")),
            None,
        )


def _submit(provider_name: str, records: list[dict[str, Any]]) -> None:
    batch = Batch.find(f"{provider_name}-opds") or Batch.new(f"{provider_name}-opds")
    batch.add_items([{"ia_id": rec["source_records"][0], "data": rec} for rec in records])


def harvest_feed(
    feed: FeedRegistry,
    session: requests.Session | None = None,
    max_pages: int | None = None,
    now: datetime.datetime | None = None,
) -> dict[str, Any]:
    """Harvest one feed: fetch -> parse -> submit to import_item -> advance cursor."""
    session = session or requests.Session()
    now = now or datetime.datetime.now(datetime.UTC)
    since = _as_utc(feed.get("last_updated")) or EPOCH
    parser_feed = feed.to_feed()
    client_cursor = feed.cursor_style != CURSOR_MODIFIED_SINCE

    records: list[dict[str, Any]] = []
    max_modified = since
    for page in iter_pages(request_url(feed, since), session, max_pages=max_pages):
        for raw in page.get("publications") or []:
            # One malformed publication (bad timestamp, link missing href, non-dict
            # entry) must not abort the page/feed: that would leave the cursor
            # un-advanced and re-poison every subsequent cycle. Skip and continue.
            try:
                pub = opds.Publication(**raw)
                modified = _as_utc(pub.modified)
                if client_cursor and modified is not None:
                    if modified <= since:
                        continue
                    max_modified = max(max_modified, modified)
                if record := opds.to_import_record(pub, parser_feed):
                    records.append(record)
            except Exception:
                logger.exception("skipping malformed publication in %s", feed.provider_name)

    if records:
        _submit(feed.provider_name, records)

    new_cursor = max_modified if (client_cursor and max_modified > since) else now
    FeedRegistry.advance(feed.id, last_updated=new_cursor.replace(tzinfo=None))
    logger.info("harvested %s: %d records", feed.provider_name, len(records))
    return {"feed": feed.provider_name, "records": len(records)}


def harvest_all(session: requests.Session | None = None, max_pages: int | None = None) -> list[dict[str, Any]]:
    """Harvest every registered feed once (the bookworm cron tick).

    Each feed is isolated: one feed erroring (network, parse, submit) is logged
    and reported, but must not starve the feeds that follow it.
    """
    results: list[dict[str, Any]] = []
    for feed in FeedRegistry.all():
        try:
            results.append(harvest_feed(feed, session=session, max_pages=max_pages))
        except Exception:
            logger.exception("harvest failed for %s", feed.provider_name)
            results.append({"feed": feed.provider_name, "records": 0, "error": True})
    return results
