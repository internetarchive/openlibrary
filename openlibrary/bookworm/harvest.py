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
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from openlibrary.bookworm import opds
from openlibrary.bookworm.registry import FeedRegistry
from openlibrary.core.acquisitions import Acquisition
from openlibrary.core.imports import Batch

logger = logging.getLogger("openlibrary.bookworm.harvest")

SUBMIT_BATCH_SIZE = 1000
"""Flush staged records to ``import_item`` every N records rather than at the end.

A backfill from the beginning is ~78k publications for Gutenberg. Accumulating
all of them before a single ``_submit`` meant holding the whole feed in memory,
then one ``WHERE ia_id IN (...)`` dedupe query and one ``multiple_insert`` of
that size. Flushing as we page bounds both.

Safe to flush mid-crawl because the cursor only advances after the whole feed
succeeds: a failure partway through re-fetches from the same cursor next run and
re-submits, where ``Batch.add_items`` drops what is already present.
"""

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


MAX_RETRIES = 3
RETRY_BACKOFF = 1.0
RETRY_STATUSES = (429, 500, 502, 503, 504)


def build_session() -> requests.Session:
    """A session that identifies itself to providers and rides out blips.

    Proxying is deliberately NOT configured here. ``setup_requests()`` exports
    ``http_proxy``/``no_proxy_addresses`` from ``openlibrary.yml`` into the
    environment (the pattern coverstore, add_book and affiliate_server all use),
    and ``requests`` reads the environment itself. So this works whether the
    proxy comes from the config file or is already set in the container env,
    and there is one place that knows how OL expresses proxy settings.
    """
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    # A backfill from the beginning is thousands of sequential fetches, and a
    # single transient failure aborts the whole crawl. That is safe -- the
    # cursor does not advance, so the next run resumes -- but a long backfill
    # may then never finish. Retry connection/read errors, rate limits and
    # server errors, with backoff so a struggling provider is not hammered.
    #
    # 4xx is deliberately absent: a 403 is a decision, not a blip, and retrying
    # it looks like abuse. raise_on_status=False keeps raise_for_status() in
    # iter_pages as the single place a bad status becomes an exception.
    retry = Retry(
        total=MAX_RETRIES,
        connect=MAX_RETRIES,
        read=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=RETRY_STATUSES,
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
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


def _merge_counts(into: dict[str, int], counts: dict[str, int]) -> None:
    for key, value in (counts or {}).items():
        into[key] = into.get(key, 0) + value


def _describe(counts: dict[str, int]) -> str:
    return ", ".join(f"{value} {key}" for key, value in counts.items() if value) or "nothing staged"


def batch_name(feed: FeedRegistry) -> str:
    """One stable batch per feed: ``{provider_name}-opds``.

    Deliberately NOT date-scoped, unlike ``bwb_opds_imports`` and the other
    importers. That convention exists because those importers are append-only --
    a new row per import event -- so the date is the only way to ask what a given
    run brought in. A feed re-offering a record updates the existing
    ``import_item`` row rather than adding one, so a date would segment nothing
    and would fragment the per-feed view instead.

    Size is therefore bounded by the feed's corpus, not by how long we have been
    running, and ``import_item.batch_id`` is indexed. "What did this feed do
    recently" is ``import_time``, which is per record and more precise than a
    batch date.

    The name is derived rather than stored on the registry row: derivation needs
    no migration and cannot drift from the feed it names.
    """
    return f"{feed.provider_name}-opds"


def _drop_unchanged(feed: FeedRegistry, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop records whose acquisitions already match what is stored.

    The feed's own ``modified`` is the first gate, but it is a third party's
    claim: a provider that re-publishes or reindexes its catalogue can bump
    every timestamp without changing anything. Without a second gate that would
    re-queue the entire corpus -- the firehose behaviour that previously
    overwhelmed the database.

    Compares against the acquisitions table rather than ``import_item.data``,
    which is cleared once a row completes and so cannot answer this for exactly
    the records that have been around longest.

    Records with no acquisitions are always kept: there is nothing to compare,
    and their bibliographic data may still have changed.
    """
    wanted = {rec["acquisitions"][0]["local_id"]: rec for rec in records if rec.get("acquisitions")}
    if not wanted:
        return records

    try:
        stored = Acquisition.find_many(feed.provider_name, list(wanted))
    except Exception:
        # Never let the optimisation break the harvest; worst case we re-offer
        # a record and add_or_refresh_items compares it again.
        logger.exception("could not read stored acquisitions for %s; not filtering", feed.provider_name)
        return records

    kept = []
    for rec in records:
        acquisitions = rec.get("acquisitions")
        if not acquisitions:
            kept.append(rec)
            continue
        previous = stored.get(acquisitions[0]["local_id"])
        if previous is None or previous.get("data") != acquisitions[0].get("data"):
            kept.append(rec)
    if dropped := len(records) - len(kept):
        logger.info("%s: %d record(s) unchanged since last import, not re-queued", feed.provider_name, dropped)
    return kept


def _submit(feed: FeedRegistry, records: list[dict[str, Any]]) -> dict[str, int]:
    """Queue harvested records into ``import_item`` for ImportBot to load.

    Uses ``add_or_refresh_items`` rather than ``add_items``: a feed is a change
    stream, so a record it re-offers carries an update -- a Better World Books
    price, say -- and ``add_items`` would drop it because the ``ia_id`` already
    exists. Unchanged records are still left alone, so this does not re-queue a
    corpus.
    """
    if not records:
        return {}
    kept = _drop_unchanged(feed, records)
    # Report what the durable gate dropped as "unchanged" too, so a run where
    # nothing changed says so rather than reporting silence.
    dropped = {"unchanged": len(records) - len(kept)}
    if not kept:
        return dropped
    name = batch_name(feed)
    batch = Batch.find(name) or Batch.new(name)
    counts = batch.add_or_refresh_items([{"ia_id": rec["source_records"][0], "data": rec} for rec in kept])
    counts["unchanged"] = counts.get("unchanged", 0) + dropped["unchanged"]
    return counts


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
    staged: dict[str, int] = {}
    records: list[dict[str, Any]] = []
    total = 0
    for page in iter_pages(feed.request_url(since), session, max_pages=max_pages, state=page_state):
        for raw in page.get("publications") or []:
            # The server already returned only records modified since the cursor,
            # so keep every record and ignore its timestamp.
            record, _modified = _parse_publication(raw, parser_feed, feed.provider_name)
            if record:
                records.append(record)
                total += 1
        if not dry_run and len(records) >= SUBMIT_BATCH_SIZE:
            _merge_counts(staged, _submit(feed, records))
            logger.info("%s: staged %d records so far", feed.provider_name, total)
            records = []

    if dry_run:
        logger.info("[dry run] %s: %d records, cursor left at %s", feed.provider_name, total, feed.last_updated)
        return {"feed": feed.provider_name, "records": total, "dry_run": True}

    _merge_counts(staged, _submit(feed, records))
    FeedRegistry.advance(feed.id, last_updated=now.replace(tzinfo=None))
    logger.info("harvested %s: %d records (%s)", feed.provider_name, total, _describe(staged))
    return {"feed": feed.provider_name, "records": total, **staged, **page_state}


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
    staged: dict[str, int] = {}
    records: list[dict[str, Any]] = []
    max_modified = since
    total = 0
    for page in iter_pages(feed.url, session, max_pages=max_pages, state=page_state):
        for raw in page.get("publications") or []:
            record, modified = _parse_publication(raw, parser_feed, feed.provider_name)
            if modified is not None:
                if modified <= since:
                    continue  # already seen; keep scanning (feed order isn't guaranteed)
                max_modified = max(max_modified, modified)
            if record:
                records.append(record)
                total += 1
        if not dry_run and len(records) >= SUBMIT_BATCH_SIZE:
            _merge_counts(staged, _submit(feed, records))
            logger.info("%s: staged %d records so far", feed.provider_name, total)
            records = []

    if dry_run:
        logger.info("[dry run] %s (full crawl): %d records, cursor left at %s", feed.provider_name, total, feed.last_updated)
        return {"feed": feed.provider_name, "records": total, "dry_run": True}

    _merge_counts(staged, _submit(feed, records))
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
    logger.info("harvested %s (full crawl): %d records (%s)", feed.provider_name, total, _describe(staged))
    return {"feed": feed.provider_name, "records": total, **staged, **page_state}


def harvest_all(session: requests.Session | None = None, max_pages: int | None = None, dry_run: bool = False) -> list[dict[str, Any]]:
    """Harvest every ACTIVE registered feed once (the bookworm cron tick).

    Each feed is isolated: one feed erroring (network, parse, submit) is logged
    and reported, but must not starve the feeds that follow it.

    Feeds still `pending` are skipped -- see STATUS_PENDING in registry.py.
    """
    results: list[dict[str, Any]] = []
    for feed in FeedRegistry.all():
        # Only feeds that have been explicitly activated. A newly registered
        # feed is `pending` so it can be inspected and dry-run first; harvesting
        # it by name with --provider still works in the meantime.
        if not feed.is_active:
            logger.info("skipping %s (status=%s; activate it to include it in scheduled runs)", feed.provider_name, feed.status)
            continue
        try:
            results.append(harvest_feed(feed, session=session, max_pages=max_pages, dry_run=dry_run))
        except Exception:
            logger.exception("harvest failed for %s", feed.provider_name)
            results.append({"feed": feed.provider_name, "records": 0, "error": True})
    return results
