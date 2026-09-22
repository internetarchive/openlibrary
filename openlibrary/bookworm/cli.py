#!/usr/bin/env python
"""Command line for the BookWorm feed harvest (#12844).

Three commands, all needing ``--ol-config`` because it supplies both the
database connection and -- on hosts that egress through a proxy -- the settings
without which no provider feed is reachable at all::

    python -m openlibrary.bookworm.cli harvest  --ol-config /olsystem/etc/openlibrary.yml
    python -m openlibrary.bookworm.cli register --ol-config /olsystem/etc/openlibrary.yml --show
    python -m openlibrary.bookworm.cli preview  --ol-config /olsystem/etc/openlibrary.yml --provider lenny

``harvest`` is the cron entrypoint: one pass over every active feed, then exit,
so the crontab can see a non-zero status. ``register`` puts the feed list in git
rather than in hand-typed SQL. ``preview`` reports what the catalog would match
without writing anything, for diagnosing a feed that looks wrong.

Run ``<command> --help`` for each one's options. The harvest logic itself is in
``harvest.py``; this module is only the interface to it.
"""

import datetime
import logging
import sys
import time
from collections import Counter
from collections.abc import Callable
from urllib.parse import urlparse

from infogami import config
from openlibrary.bookworm import harvest
from openlibrary.bookworm.registry import (
    CURSOR_MODIFIED_SINCE,
    STATUS_ACTIVE,
    FeedRegistry,
)
from openlibrary.catalog.add_book import load
from openlibrary.config import load_config
from openlibrary.plugins.upstream.utils import setup_requests
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.bookworm.cli")


# ---------------------------------------------------------------------------
# harvest
# ---------------------------------------------------------------------------

DEFAULT_INTERVAL_SECONDS = 3600
MIN_INTERVAL_SECONDS = 60
"""Floor for --continuous. Zero would hammer provider feeds from a production host."""


def _check_proxy_is_parsable() -> None:
    """Reject a malformed ``http_proxy`` before it can leak into a log.

    The configured proxy URL embeds a password. urllib3 raises
    ``LocationParseError`` containing the whole URL for some malformed values
    (a non-numeric port, say), and harvest_all logs every feed failure with
    logger.exception -- which would write the credential into the cron log and,
    where MAILTO is set, into cron mail. Failing here costs one startup check.
    """
    if not (proxy := config.get("http_proxy")):
        return
    try:
        parsed = urlparse(proxy)
        _ = parsed.port  # raises ValueError on a non-numeric port
    except ValueError:
        # Deliberately does not echo the value.
        raise SystemExit("http_proxy in openlibrary.yml is malformed; refusing to start (value not shown)") from None
    if not parsed.hostname:
        raise SystemExit("http_proxy in openlibrary.yml has no host; refusing to start (value not shown)")


def _run_pass(provider: str | None, max_pages: int | None, dry_run: bool) -> list[dict]:
    """One harvest pass over the selected feed(s)."""
    if not provider:
        return harvest.harvest_all(max_pages=max_pages, dry_run=dry_run)

    feeds = [feed for feed in FeedRegistry.all() if feed.provider_name == provider]
    if not feeds:
        logger.error("no registered feed named %r", provider)
        raise SystemExit(1)

    # Same per-feed isolation harvest_all provides, so a single feed's failure
    # is reported as a result rather than an uncaught traceback -- and so
    # --dry-run behaves identically whether or not --provider is given.
    results = []
    for feed in feeds:
        try:
            results.append(harvest.harvest_feed(feed, max_pages=max_pages, dry_run=dry_run))
        except Exception:
            logger.exception("harvest failed for %s", feed.provider_name)
            results.append({"feed": feed.provider_name, "records": 0, "error": True})
    return results


def _report(results: list[dict], dry_run: bool) -> bool:
    """Log one line per feed. Returns True if any feed errored.

    Per-feed rather than a single summary because the failure that matters here
    is one provider breaking while the others keep working — which a summary
    line, or an exit code alone, hides completely.
    """
    if not results:
        logger.warning("no feeds registered; nothing to harvest (see the register command)")
        return False

    failed = False
    for result in results:
        if result.get("truncated"):
            logger.warning(
                "feed %s was TRUNCATED -- the cursor advanced past pages that were never fetched. Reset its last_updated to re-harvest them.",
                result.get("feed"),
            )
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


def harvest_command(
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
    # Exports http_proxy / no_proxy_addresses from openlibrary.yml into the
    # environment, where requests picks them up. ol-home0 reaches provider
    # feeds only through an authenticated proxy, so without this every fetch
    # fails -- and the credentials stay in the config file rather than the
    # container environment.
    setup_requests()
    _check_proxy_is_parsable()

    if not continuous:
        failed = _report(_run_pass(provider, max_pages, dry_run), dry_run)
        # Any feed failing is worth cron's attention: exiting non-zero only when
        # *every* feed errors makes a single broken provider silently invisible.
        # A dry run reports instead of failing -- it is a diagnostic, not a job.
        if failed and not dry_run:
            raise SystemExit(1)
        return

    if interval < MIN_INTERVAL_SECONDS:
        logger.warning("--interval %ds is below the %ds floor; using the floor", interval, MIN_INTERVAL_SECONDS)
        interval = MIN_INTERVAL_SECONDS
    logger.info("bookworm harvest starting in continuous mode (every %ds)", interval)
    while True:
        try:
            _report(_run_pass(provider, max_pages, dry_run), dry_run)
        except KeyboardInterrupt:
            logger.info("bookworm harvest stopped")
            return
        except SystemExit:
            # Not a clean shutdown. Catching this alongside KeyboardInterrupt
            # returned 0, so a supervisor read a fatal config error as a
            # successful stop and never restarted or alerted. Let it propagate
            # with its own status.
            logger.error("bookworm harvest exiting on a fatal error")
            raise
        except Exception:
            # A long-running loop must outlive a transient failure; the next
            # pass resumes from the same cursor, so nothing is lost.
            logger.exception("harvest pass failed; continuing")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("bookworm harvest stopped")
            return


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

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


def register_command(
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


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------

MATCHED_EXPECTED = "matched the expected edition"
MATCHED_OTHER = "matched a DIFFERENT edition"
WOULD_CREATE = "would CREATE a new edition"
NO_ANSWER = "no edition resolved"


def expected_edition_key(record: dict) -> str | None:
    """The edition a record names, or None if it names none.

    Prefers the ``openlibrary`` field, which is what the catalog is actually
    handed, so a match against it means the id was honoured rather than
    coincidentally agreed with. Falls back to the acquisition's ``local_id`` so
    the tool still reports a split for a feed registered before
    ``local_id_is_ol_edition`` existed -- which is one of the failures worth
    catching.
    """
    if ol_id := record.get("openlibrary"):
        return f"/books/{ol_id}"
    acquisitions = record.get("acquisitions") or []
    local_id = acquisitions[0].get("local_id") if acquisitions else None
    if not local_id or not str(local_id).isdigit():
        return None
    return f"/books/OL{local_id}M"


def classify(record: dict, reply: dict, expect_edition_ids: bool = True) -> tuple[str, str | None, str | None]:
    """Bucket one preview result. Returns (bucket, matched_key, expected_key)."""
    edition = (reply or {}).get("edition") or {}
    matched_key = edition.get("key")
    status = edition.get("status")

    if not matched_key:
        return NO_ANSWER, None, None
    if status == "created":
        return WOULD_CREATE, matched_key, None

    expected = expected_edition_key(record) if expect_edition_ids else None
    if expected is None:
        return MATCHED_EXPECTED, matched_key, None  # nothing to compare against
    if matched_key == expected:
        return MATCHED_EXPECTED, matched_key, expected
    return MATCHED_OTHER, matched_key, expected


def preview_command(
    ol_config: str = "/openlibrary/conf/openlibrary.yml",
    provider: str = "",
    limit: int | None = None,
    expect_edition_ids: bool = True,
    verbose: bool = False,
) -> None:
    """Report which edition the catalog would match for each of a feed's records.

    A diagnostic, and it writes nothing: ``load(rec, save=False)`` makes the
    full match/merge decision but never reaches ``_save_acquisitions``, and both
    ``add_cover`` call sites are gated on ``save``.

    Useful where matching is genuinely a guess -- a feed that does NOT name an
    edition is pooled on title alone, and these collections are the most
    duplicated records in the catalog, so a wrong pick is likely and silent.
    For a feed that DOES name its edition there is nothing to second-guess per
    record; the buckets then only tell you whether the id reached the catalog
    and resolved.

    Not free: one Infobase read and one solr query per record.

    :param ol_config: path to ``openlibrary.yml``.
    :param provider: the registered feed to preview. Required.
    :param limit: stop after this many records.
    :param expect_edition_ids: treat a numeric ``local_id`` as naming the OL
        edition, and report exact match vs wrong edition. True suits Lenny.
    :param verbose: print a line per record, not just the summary.
    """
    logging.basicConfig(level=logging.INFO)
    load_config(ol_config)
    setup_requests()

    if not provider:
        logger.error("--provider is required")
        raise SystemExit(1)
    feeds = [f for f in FeedRegistry.all() if f.provider_name == provider]
    if not feeds:
        logger.error("no registered feed named %r", provider)
        raise SystemExit(1)
    feed = feeds[0]

    session = harvest.build_session()
    parser_feed = feed.to_feed()
    records = []
    for page in harvest.iter_pages(feed.url, session):
        for raw in page.get("publications") or []:
            record, _modified = harvest._parse_publication(raw, parser_feed, feed.provider_name)
            if record:
                records.append(record)
            if limit and len(records) >= limit:
                break
        if limit and len(records) >= limit:
            break

    logger.info("previewing %d records from %s -- nothing will be written", len(records), provider)
    buckets: Counter[str] = Counter()
    wrong: list[tuple[str, str, str]] = []
    for record in records:
        source = (record.get("source_records") or ["?"])[0]
        try:
            reply = load(dict(record), save=False)
        except Exception:
            logger.exception("preview failed for %s", source)
            buckets[NO_ANSWER] += 1
            continue
        bucket, matched, expected = classify(record, reply, expect_edition_ids)
        buckets[bucket] += 1
        if bucket == MATCHED_OTHER and matched and expected:
            wrong.append((source, expected, matched))
        if verbose:
            logger.info("  %s -> %s (%s)", source, matched, bucket)

    print(f"\n{provider}: {len(records)} records previewed, nothing written\n")
    for bucket, count in buckets.most_common():
        print(f"  {count:5d}  {bucket}")
    if wrong:
        print(f"\n  {len(wrong)} attached to the wrong edition -- first 10:")
        for source, expected, matched in wrong[:10]:
            print(f"    {source}: expected {expected}, matched {matched}")
        print("\n  A wrong-edition match reports no error and looks successful, so this")
        print("  is the bucket to act on. For a feed registered with local_id_is_ol_edition")
        print("  it means the id never reached the catalog -- check the row with `register --show`.")


# ---------------------------------------------------------------------------

COMMANDS: dict[str, Callable[..., None]] = {
    "harvest": harvest_command,
    "register": register_command,
    "preview": preview_command,
}


def main(argv: list[str] | None = None) -> None:
    """Dispatch to one of COMMANDS, then let FnToCLI handle its flags.

    FnToCLI derives a parser from a single function signature, so each command
    keeps its own flags and docstring rather than sharing one flattened parser
    where half the options are meaningless.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help") or args[0] not in COMMANDS:
        print(f"usage: python -m openlibrary.bookworm.cli {{{'|'.join(COMMANDS)}}} [options]")
        print("\nRun '<command> --help' for a command's options.")
        raise SystemExit(0 if args and args[0] in ("-h", "--help", "help") else 2)
    command = FnToCLI(COMMANDS[args[0]])
    # Otherwise every command's --help claims the bare module as its usage.
    command.parser.prog = f"python -m openlibrary.bookworm.cli {args[0]}"
    command.parse_args(args[1:])
    command.run()


if __name__ == "__main__":
    main()
