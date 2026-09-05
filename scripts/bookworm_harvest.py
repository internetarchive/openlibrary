#!/usr/bin/env python
"""BookWorm feed-harvest cron entrypoint (#12844).

Harvests the registered feeds: fetch each feed, parse its publications into Open
Library import records (carrying ``acquisitions[]``), and submit them to the
``import_item`` queue. ImportBot (``manage-imports import-all``) then loads them
and the catalog writes the acquisitions.

Two ways to run it:

**One pass, then exit** — the default, and how prod runs it. Scheduling belongs
to the crontab, which can see a non-zero exit::

    python scripts/bookworm_harvest.py --ol-config /olsystem/etc/openlibrary.yml

**Continuously** — for a supervised process or a long soak test, harvesting
every ``--interval`` seconds until interrupted::

    python scripts/bookworm_harvest.py --ol-config /olsystem/etc/openlibrary.yml \\
        --continuous --interval 3600

Either mode can be narrowed to one feed with ``--provider``, which resumes from
that feed's own cursor, so a single provider can be caught up or retried without
touching the others.

``--dry-run`` fetches and parses but writes nothing — no import items, no cursor
advance — so a new feed can be validated against production before it is allowed
to write.

The harvest logic itself lives in ``openlibrary/bookworm/harvest.py``.
"""

import logging
import time

from openlibrary.bookworm import harvest
from openlibrary.bookworm.registry import FeedRegistry
from openlibrary.config import load_config
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.bookworm.cron")

DEFAULT_INTERVAL_SECONDS = 3600


def _run_pass(provider: str | None, max_pages: int | None, dry_run: bool) -> list[dict]:
    """One harvest pass over the selected feed(s)."""
    if not provider:
        return harvest.harvest_all(max_pages=max_pages, dry_run=dry_run)

    feeds = [feed for feed in FeedRegistry.all() if feed.provider_name == provider]
    if not feeds:
        logger.error("no registered feed named %r", provider)
        raise SystemExit(1)
    return [harvest.harvest_feed(feed, max_pages=max_pages, dry_run=dry_run) for feed in feeds]


def _report(results: list[dict], dry_run: bool) -> bool:
    """Log one line per feed. Returns True if any feed errored.

    Per-feed rather than a single summary because the failure that matters here
    is one provider breaking while the others keep working — which a summary
    line, or an exit code alone, hides completely.
    """
    failed = False
    for result in results:
        if result.get("error"):
            failed = True
            logger.error("feed %s FAILED (see traceback above)", result.get("feed"))
        else:
            logger.info(
                "feed %s: %d records%s",
                result.get("feed"),
                result.get("records", 0),
                " (dry run, nothing written)" if dry_run else "",
            )
    return failed


def main(
    ol_config: str = "/openlibrary/conf/openlibrary.yml",
    provider: str | None = None,
    continuous: bool = False,
    interval: int = DEFAULT_INTERVAL_SECONDS,
    max_pages: int | None = None,
    dry_run: bool = False,
) -> None:
    """Harvest the registered BookWorm feeds.

    :param ol_config: path to ``openlibrary.yml``. Supplies the database
        connection and, on hosts that egress through a proxy, the proxy settings
        the harvester needs to reach provider feeds at all.
    :param provider: harvest only this feed by ``provider_name``, resuming from
        its own cursor; default is every registered feed.
    :param continuous: keep harvesting every ``interval`` seconds instead of
        exiting after one pass. For a supervised process; cron should use the
        default single-pass mode so it can see the exit status.
    :param interval: seconds between passes in ``continuous`` mode.
    :param max_pages: cap pages fetched per feed. TESTING ONLY — truncating a
        crawl advances the cursor past the pages it didn't fetch, permanently
        skipping them. Reset that feed's ``last_updated`` afterwards.
    :param dry_run: fetch and parse but write nothing — no import items and no
        cursor advance.
    """
    logging.basicConfig(level=logging.INFO)
    load_config(ol_config)

    if not continuous:
        failed = _report(_run_pass(provider, max_pages, dry_run), dry_run)
        # Any feed failing is worth cron's attention: exiting non-zero only when
        # *every* feed errors makes a single broken provider silently invisible.
        # A dry run reports instead of failing -- it is a diagnostic, not a job.
        if failed and not dry_run:
            raise SystemExit(1)
        return

    logger.info("bookworm harvest starting in continuous mode (every %ds)", interval)
    while True:
        try:
            _report(_run_pass(provider, max_pages, dry_run), dry_run)
        except KeyboardInterrupt, SystemExit:
            logger.info("bookworm harvest stopped")
            return
        except Exception:
            # A long-running loop must outlive a transient failure; the next
            # pass resumes from the same cursor, so nothing is lost.
            logger.exception("harvest pass failed; continuing")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("bookworm harvest stopped")
            return


if __name__ == "__main__":
    FnToCLI(main).run()
