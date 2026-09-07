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

Feeds register as ``pending`` and scheduled runs skip them, so registering is
safe. Validate first, then activate::

    python scripts/bookworm_harvest.py --ol-config ... --provider lenny --dry-run
    python scripts/bookworm_register.py --ol-config ... --provider lenny --activate
"""

import datetime
import logging

from openlibrary.bookworm.registry import CURSOR_MODIFIED_SINCE, STATUS_ACTIVE, FeedRegistry
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
        # Lenny's self-link id IS the OL edition number (/opds/51008637 ->
        # /books/OL51008637M, verified: "The Art of War"), so records can name
        # their edition instead of being matched on title alone.
        "local_id_is_ol_edition": True,
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

Better World Books is deliberately excluded. As of 2026-09-05 its feed returns
403 from Cloudflare. Confirmed on the Squid side that this is NOT our proxy
denying it -- the access log shows the CONNECT allowed and tunnelled
(TCP_TUNNEL/200), so the 403 comes from Cloudflare inside the TLS tunnel.
Whether that is IP reputation or bot-signature is not established. Registering
it would make every harvest pass report a failing feed; add it with
``--provider betterworldbooks`` once BWB allowlists us.
"""


def main(
    ol_config: str = "/openlibrary/conf/openlibrary.yml",
    provider: str | None = None,
    since: str | None = None,
    reseed: bool = False,
    activate: bool = False,
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
    :param activate: mark the feed active so scheduled runs harvest it. Feeds
        register as ``pending`` and are skipped by ``harvest_all`` until this is
        set, which is what lets you dry-run one before it can write.
    :param reseed: allow ``--since`` to move the cursor of an ALREADY registered
        feed. Off by default so a routine re-run can never replay history; the
        recovery path for "registered it, then realised the backfill is too
        large" without hand-written SQL.
    :param dry_run: report what would be registered without writing.
    """
    logging.basicConfig(level=logging.INFO)
    load_config(ol_config)

    if show:
        feeds = [f for f in FeedRegistry.all() if not provider or f.provider_name == provider]
        if not feeds:
            print("feed_registry is empty")
        for row in feeds:
            print(f"#{row.id} {row.provider_name}  [{row.status}]\n    url={row.url}\n    last_updated={row.last_updated}\n    data={row.data}")
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

        # register() is keyed on provider_name + url, so editing a feed's URL
        # creates a SECOND live row for the same provider -- both harvested
        # every pass, with independent cursors, competing for the same batch.
        if stale := [f for f in FeedRegistry.all() if f.provider_name == name and f.url != spec["url"]]:
            logger.warning(
                "%s is already registered at a DIFFERENT url: %s. Registering %s as well leaves both live; delete the stale row if it is superseded.",
                name,
                ", ".join(f.url for f in stale),
                spec["url"],
            )

        existing = FeedRegistry.find(name, spec["url"])
        extra = {k: v for k, v in spec.items() if k not in ("url", "id_strategy", "cursor_style")}
        if existing:
            # register() is idempotent and returns the existing row WITHOUT
            # touching its data blob, so connector config added to FEEDS after a
            # feed was first registered never reaches the database. Silent, and
            # the symptom (records matched on title alone because
            # local_id_is_ol_edition never arrived) looks nothing like the cause.
            drift = {
                k: v for k, v in {"id_strategy": spec["id_strategy"], "cursor_style": spec["cursor_style"], **extra}.items() if (existing.data or {}).get(k) != v
            }
            if drift:
                logger.warning(
                    "%s is registered with stale connector config; %s will NOT be applied. Delete the row and re-register to pick it up.",
                    name,
                    drift,
                )
        feed: FeedRegistry | None = FeedRegistry.register(
            name,
            spec["url"],
            id_strategy=spec["id_strategy"],
            cursor_style=spec["cursor_style"],
            data=extra or None,
        )
        if feed is None:
            logger.error("failed to register %s", name)
            raise SystemExit(1)
        logger.info("%s %s (id=%d)", "already registered:" if existing else "registered:", name, feed.id)

        # Only seed a cursor on first registration; re-running must never rewind
        # a feed that has already made progress.
        if activate:
            FeedRegistry.set_status(feed.id, STATUS_ACTIVE)
            logger.info("    activated: scheduled runs will now harvest %s", name)
        else:
            logger.info("    status=%s (not harvested by scheduled runs; re-run with --activate)", feed.status)

        if cursor and (not existing or reseed):
            FeedRegistry.advance(feed.id, last_updated=cursor)
            logger.info("    %s cursor to %s", "reseeded" if existing else "seeded", cursor.date())
        elif cursor and existing:
            logger.warning(
                "    --since ignored: %s is already registered with cursor %s. Re-run with --reseed to move it.",
                name,
                feed.last_updated,
            )


if __name__ == "__main__":
    FnToCLI(main).run()
