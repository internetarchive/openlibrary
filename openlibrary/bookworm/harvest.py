"""BookWorm feed harvesting (#12844).

Fetch a registered feed, parse its publications into Open Library import records
(carrying ``acquisitions[]``), and submit them to OL's existing ``import_item``
queue via :class:`~openlibrary.core.imports.Batch`. ImportBot (manage-imports)
then loads them, and the catalog writes the acquisitions.

:func:`harvest_feed` dispatches on how the feed lets us fetch only what changed:

- **Native** (:func:`_harvest_native`) — the feed filters server-side via
  ``?modified_since=<cursor>`` (Gutenberg, Lenny). Fetch, parse, submit, advance
  the cursor to the run time.
- **Fallback** (:func:`_harvest_by_full_crawl`) — the feed has no such param
  (currently only BWB), so crawl it in full and filter by each publication's
  ``modified`` timestamp on our side. Strictly worse; meant to be deleted once
  every feed supports ``modified_since``.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import requests

from openlibrary.bookworm import opds
from openlibrary.bookworm.registry import FeedRegistry
from openlibrary.core.imports import Batch

logger = logging.getLogger("openlibrary.bookworm.harvest")

REQUEST_TIMEOUT = 60
EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)

USER_AGENT = "OpenLibraryBot/1.0 (+https://openlibrary.org; openlibrary@archive.org)"
"""Identify ourselves to providers.

Two reasons this is not the ``requests`` default. Cloudflare (in front of Better
World Books) commonly blocks ``python-requests/x.y.z``, and a provider that
wants to allowlist our crawler needs a stable name and a contact address to
allowlist it *by*. Note the BWB 403 has not been traced to the User-Agent
specifically -- see scripts/bookworm_register.py for what was actually
confirmed.
"""


def build_session() -> requests.Session:
    """A session that identifies itself to providers.

    Proxying is deliberately NOT configured here. ``setup_requests()`` exports
    ``http_proxy``/``no_proxy_addresses`` from ``openlibrary.yml`` into the
    environment (the pattern coverstore, add_book and affiliate_server all use),
    and ``requests`` reads the environment itself. So this works whether the
    proxy comes from the config file or is already set in the container env,
    and there is one place that knows how OL expresses proxy settings.
    """
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def _as_utc(value: datetime.datetime | str | None) -> datetime.datetime | None:
    if not value:
        return None
    dt = datetime.datetime.fromisoformat(value) if isinstance(value, str) else value
    return dt.replace(tzinfo=datetime.UTC) if dt.tzinfo is None else dt.astimezone(datetime.UTC)


def iter_pages(start_url: str, session: requests.Session, max_pages: int | None = None, state: dict | None = None):
    """Yield OPDS pages, following ``rel=next``.

    Stopping early -- a pagination loop, or the ``max_pages`` cap -- is
    indistinguishable from reaching the end of the feed, and the caller advances
    the cursor either way. So record it in ``state`` when it happens: a
    truncated crawl that silently advances the cursor skips every page it never
    fetched, permanently.
    """
    url: str | None = start_url
    seen: set[str] = set()
    page_num = 0
    while url:
        if url in seen:
            logger.warning("pagination loop at %s; stopping (cursor will advance past unfetched pages)", url)
            if state is not None:
                state["truncated"] = True
            return
        seen.add(url)
        page_num += 1
        if max_pages is not None and page_num > max_pages:
            if state is not None:
                state["truncated"] = True
            return
        resp = session.get(url, timeout=REQUEST_TIMEOUT, headers={"Accept": "application/opds+json"})
        resp.raise_for_status()
        page = resp.json()
        yield page
        url = next(
            (link["href"] for link in (page.get("links") or []) if link.get("rel") == "next" and link.get("href")),
            None,
        )


def _parse_publication(raw: dict, feed: opds.Feed, provider_name: str) -> tuple[dict[str, Any] | None, datetime.datetime | None]:
    """Parse one OPDS publication into (import record | None, modified timestamp).

    Isolated so a single malformed publication (bad timestamp, link missing
    ``href``, non-dict entry) is skipped rather than aborting the whole feed —
    which would leave the cursor un-advanced and re-poison every later run.
    """
    try:
        pub = opds.Publication(**raw)
        return opds.to_import_record(pub, feed), _as_utc(pub.modified)
    except Exception:
        logger.exception("skipping malformed publication in %s", provider_name)
        return None, None


def _submit(feed: FeedRegistry, records: list[dict[str, Any]]) -> None:
    """Queue harvested records into ``import_item`` for ImportBot to load."""
    if not records:
        return
    batch = Batch.find(f"{feed.provider_name}-opds") or Batch.new(f"{feed.provider_name}-opds")
    batch.add_items([{"ia_id": rec["source_records"][0], "data": rec} for rec in records])


def harvest_feed(
    feed: FeedRegistry,
    session: requests.Session | None = None,
    max_pages: int | None = None,
    now: datetime.datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Harvest one feed, using the native ``modified_since`` path when supported.

    ``max_pages`` is a testing cap only: truncating a crawl advances the cursor
    past the pages it didn't fetch, permanently skipping them — don't use it in
    production.
    """
    if feed.supports_modified_since:
        return _harvest_native(feed, session=session, max_pages=max_pages, now=now, dry_run=dry_run)
    return _harvest_by_full_crawl(feed, session=session, max_pages=max_pages, now=now, dry_run=dry_run)


def _harvest_native(
    feed: FeedRegistry,
    session: requests.Session | None = None,
    max_pages: int | None = None,
    now: datetime.datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Harvest a feed that filters server-side via ``?modified_since=<cursor>``."""
    session = session or build_session()
    now = now or datetime.datetime.now(datetime.UTC)
    since = _as_utc(feed.last_updated) or EPOCH
    parser_feed = feed.to_feed()

    page_state: dict = {}
    records: list[dict[str, Any]] = []
    for page in iter_pages(feed.request_url(since), session, max_pages=max_pages, state=page_state):
        for raw in page.get("publications") or []:
            # The server already returned only records modified since the cursor,
            # so keep every record and ignore its timestamp.
            record, _modified = _parse_publication(raw, parser_feed, feed.provider_name)
            if record:
                records.append(record)

    if dry_run:
        logger.info("[dry run] %s: %d records, cursor left at %s", feed.provider_name, len(records), feed.last_updated)
        return {"feed": feed.provider_name, "records": len(records), "dry_run": True}

    _submit(feed, records)
    FeedRegistry.advance(feed.id, last_updated=now.replace(tzinfo=None))
    logger.info("harvested %s: %d records", feed.provider_name, len(records))
    return {"feed": feed.provider_name, "records": len(records), **page_state}


def _harvest_by_full_crawl(
    feed: FeedRegistry,
    session: requests.Session | None = None,
    max_pages: int | None = None,
    now: datetime.datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Fallback for feeds WITHOUT a ``modified_since`` filter (currently only BWB).

    Deliberately parallel to :func:`_harvest_native` rather than sharing its body:
    it crawls the whole feed every run and filters by each publication's
    ``modified`` timestamp on our side. Delete this function as a unit once every
    feed supports ``modified_since``.
    """
    session = session or build_session()
    now = now or datetime.datetime.now(datetime.UTC)
    since = _as_utc(feed.last_updated) or EPOCH
    parser_feed = feed.to_feed()

    page_state: dict = {}
    records: list[dict[str, Any]] = []
    max_modified = since
    for page in iter_pages(feed.url, session, max_pages=max_pages, state=page_state):
        for raw in page.get("publications") or []:
            record, modified = _parse_publication(raw, parser_feed, feed.provider_name)
            if modified is not None:
                if modified <= since:
                    continue  # already seen; keep scanning (feed order isn't guaranteed)
                max_modified = max(max_modified, modified)
            if record:
                records.append(record)

    if dry_run:
        logger.info("[dry run] %s (full crawl): %d records, cursor left at %s", feed.provider_name, len(records), feed.last_updated)
        return {"feed": feed.provider_name, "records": len(records), "dry_run": True}

    _submit(feed, records)
    # Advance to the newest modified we saw; if nothing was newer, advance to now
    # so an idle feed doesn't re-scan from the same old cursor every run.
    #
    # Clamped to `now`: one publication with a bad `modified` (a provider typo,
    # a bad epoch conversion, clock skew) would otherwise park the cursor in the
    # future. Every subsequent run then filters out every real record, and the
    # `else now` fallback quietly "recovers" the cursor to the present -- so the
    # entire back-catalogue ends up below the cursor and is never harvested
    # again, with no error and a zero exit.
    new_cursor = min(max_modified, now) if max_modified > since else now
    FeedRegistry.advance(feed.id, last_updated=new_cursor.replace(tzinfo=None))
    logger.info("harvested %s (full crawl): %d records", feed.provider_name, len(records))
    return {"feed": feed.provider_name, "records": len(records), **page_state}


def harvest_all(session: requests.Session | None = None, max_pages: int | None = None, dry_run: bool = False) -> list[dict[str, Any]]:
    """Harvest every registered feed once (the bookworm cron tick).

    Each feed is isolated: one feed erroring (network, parse, submit) is logged
    and reported, but must not starve the feeds that follow it.
    """
    results: list[dict[str, Any]] = []
    for feed in FeedRegistry.all():
        try:
            results.append(harvest_feed(feed, session=session, max_pages=max_pages, dry_run=dry_run))
        except Exception:
            logger.exception("harvest failed for %s", feed.provider_name)
            results.append({"feed": feed.provider_name, "records": 0, "error": True})
    return results
