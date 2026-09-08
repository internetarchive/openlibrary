#!/usr/bin/env python
"""BookWorm feed-harvest cron entrypoint (#12844).

Runs ONE harvest pass over the registered feeds: fetch each feed, parse its
publications into Open Library import records (carrying ``acquisitions[]``), and
submit them to the ``import_item`` queue. ImportBot (``manage-imports
import-all``) then loads them and the catalog writes the acquisitions.

This is the v1 runner: a periodic cron on the ol-home0 cron container, e.g.

    python scripts/bookworm_harvest.py --ol-config /olsystem/etc/openlibrary.yml

Scheduling is the crontab's job (hourly in prod), so this exits after one pass
rather than looping. Pass ``--provider`` to harvest a single feed when testing.
The harvest logic itself lives in ``openlibrary/bookworm/harvest.py``.
"""

import logging

from openlibrary.bookworm import harvest
from openlibrary.bookworm.registry import FeedRegistry
from openlibrary.config import load_config
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.bookworm.cron")


def main(
    ol_config: str = "/openlibrary/conf/openlibrary.yml",
    provider: str | None = None,
    max_pages: int | None = None,
) -> None:
    """Run one BookWorm harvest pass.

    :param ol_config: path to ``openlibrary.yml`` (for the database connection).
    :param provider: harvest only this feed by ``provider_name``; default is all.
    :param max_pages: cap pages fetched per feed. TESTING ONLY — truncating a
        crawl advances the cursor past the pages it didn't fetch.
    """
    logging.basicConfig(level=logging.INFO)
    load_config(ol_config)
    if provider:
        feeds = [feed for feed in FeedRegistry.all() if feed.provider_name == provider]
        if not feeds:
            logger.error("no registered feed named %r", provider)
            raise SystemExit(1)
        results = [harvest.harvest_feed(feed, max_pages=max_pages) for feed in feeds]
    else:
        results = harvest.harvest_all(max_pages=max_pages)
    logger.info("bookworm harvest complete: %s", results)
    # Surface a total failure to cron (every feed errored) with a non-zero exit.
    if results and all(result.get("error") for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    FnToCLI(main).run()
