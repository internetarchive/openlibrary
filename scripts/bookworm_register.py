#!/usr/bin/env python
"""Register BookWorm provider feeds in ``feed_registry`` (#12844).

The feeds Open Library harvests are configuration, so they live here in git
where they can be reviewed and re-applied, rather than as hand-typed SQL pasted
into a ticket. Registration is idempotent (``FeedRegistry.register`` is keyed on
``provider_name`` + ``url``), so this is safe to re-run.

    # see what is registered now
    python scripts/bookworm_register.py --ol-config /olsystem/etc/openlibrary.yml --show

    # register the default feeds
    python scripts/bookworm_register.py --ol-config /olsystem/etc/openlibrary.yml

    # register one feed, seeding its cursor to bound the first backfill
    python scripts/bookworm_register.py --ol-config /olsystem/etc/openlibrary.yml \\
        --provider project_gutenberg --since 2026-08-28

A registered feed is **live on the next harvest** -- ``FeedRegistry.all()`` has
no status filter -- so register a feed only when you are ready for it to run,
and use ``bookworm_harvest.py --dry-run --provider <name>`` to validate it first.
"""

import datetime
import logging

from openlibrary.bookworm.registry import CURSOR_MODIFIED_SINCE, FeedRegistry
from openlibrary.config import load_config
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.bookworm.register")

FEEDS: dict[str, dict] = {
    "lenny": {
        "url": "https://lennyforlibraries.org/v1/api/opds",
        "id_strategy": "self_link",
        # Verified 2026-09-04: honours ?modified_since (96 items unfiltered, 0
        # since 2026-09-01), so it does not need a full crawl each run.
        "cursor_style": CURSOR_MODIFIED_SINCE,
    },
    "project_gutenberg": {
        "url": "https://opds-test.pglaf.org/opds/search?sort=fil",
        "id_strategy": "gutenberg",
        "cursor_style": CURSOR_MODIFIED_SINCE,
    },
    "betterworldbooks": {
        "url": "https://www.betterworldbooks.com/opds",
        "id_strategy": "isbn",
        # No modified_since param, so this one is crawled in full each run.
        "cursor_style": "client",
    },
}

DEFAULT_PROVIDERS = ("lenny", "project_gutenberg")
"""Registered by default.

Better World Books is deliberately excluded: as of 2026-09-04 its feed sits
behind Cloudflare, which blocks our proxy's egress with a 403. Registering it
would make every harvest pass report a failing feed. Add it with
``--provider betterworldbooks`` once they allowlist us.
"""


def main(
    ol_config: str = "/openlibrary/conf/openlibrary.yml",
    provider: str | None = None,
    since: str | None = None,
    show: bool = False,
    dry_run: bool = False,
) -> None:
    """Register provider feeds, or show what is already registered.

    :param ol_config: path to ``openlibrary.yml`` (for the database connection).
    :param provider: register only this feed; default is the feeds in
        ``DEFAULT_PROVIDERS``.
    :param since: seed the cursor (``YYYY-MM-DD``) so the first run doesn't
        backfill the feed's whole history. Gutenberg carries ~78k items, so an
        unseeded first run is thousands of paged fetches; a recent date makes it
        minutes, and the cursor catches up on its own.
    :param show: print the current registry and exit without writing.
    :param dry_run: report what would be registered without writing.
    """
    logging.basicConfig(level=logging.INFO)
    load_config(ol_config)

    if show:
        feeds = FeedRegistry.all()
        if not feeds:
            print("feed_registry is empty")
        for row in feeds:
            print(f"#{row.id} {row.provider_name}\n    url={row.url}\n    last_updated={row.last_updated}\n    data={row.data}")
        return

    if provider and provider not in FEEDS:
        logger.error("unknown feed %r; known feeds: %s", provider, ", ".join(sorted(FEEDS)))
        raise SystemExit(1)

    cursor = None
    if since:
        try:
            cursor = datetime.datetime.strptime(since, "%Y-%m-%d")
        except ValueError:
            logger.error("--since must be YYYY-MM-DD, got %r", since)
            raise SystemExit(1) from None

    for name in [provider] if provider else DEFAULT_PROVIDERS:
        spec = FEEDS[name]
        if dry_run:
            logger.info("[dry run] would register %s -> %s", name, spec["url"])
            continue

        existing = FeedRegistry.find(name, spec["url"])
        feed: FeedRegistry | None = FeedRegistry.register(
            name,
            spec["url"],
            id_strategy=spec["id_strategy"],
            cursor_style=spec["cursor_style"],
        )
        if feed is None:
            logger.error("failed to register %s", name)
            raise SystemExit(1)
        logger.info("%s %s (id=%d)", "already registered:" if existing else "registered:", name, feed.id)

        # Only seed a cursor on first registration; re-running must never rewind
        # a feed that has already made progress.
        if cursor and not existing:
            FeedRegistry.advance(feed.id, last_updated=cursor)
            logger.info("    seeded cursor to %s", cursor.date())
        elif cursor and existing:
            logger.info("    cursor left at %s (already registered; --since ignored)", feed.last_updated)


if __name__ == "__main__":
    FnToCLI(main).run()
