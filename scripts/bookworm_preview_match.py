#!/usr/bin/env python
"""Preview what the catalog WOULD match for a feed, writing nothing (#12844).

Answers the question that decides whether a feed is safe to let loose: for each
publication, which Open Library edition does the catalog resolve it to?

Run this before ever letting a feed write. ``add_book.load(rec, save=False)``
performs the full match/merge decision and returns the edition it settled on,
but allocates placeholder keys instead of real ones and never reaches
``_save_acquisitions`` -- so nothing is created, nothing is queued, and no
acquisition is attached.

    python scripts/bookworm_preview_match.py --ol-config /olsystem/etc/openlibrary.yml \\
        --provider lenny

Why this matters more than a status count. ``build_pool`` matches on title,
OCLC, LCCN, ocaid and ISBN, and ignores ``identifiers.*`` -- so a feed record
carrying only a title, authors and a provider id is pooled on its title alone.
Feeds of public-domain classics hit the most duplicated records in the catalog
("Frankenstein" spans thousands of works, "Alice's Adventures in Wonderland"
thousands of editions), so that pool is enormous and something in it gets
picked. The likely failure is therefore not a missing match or a duplicate
edition; it is a confident match to the WRONG edition, which looks completely
successful and reports no error.

A feed whose ``local_id`` is itself an Open Library edition number can answer
the question instead of being guessed at: registered with
``local_id_is_ol_edition``, its records carry ``openlibrary: OL<id>M``, and the
catalog narrows the pool to that edition. Lenny is such a feed (``/opds/51008637``
-> ``/books/OL51008637M``). For those feeds this tool is a verification that the
id was honoured, and each bucket has a specific meaning:

- ``matched a DIFFERENT edition`` -- the id was ignored. Usually the registered
  row predates the config (``register`` does not update an existing data blob).
- ``would CREATE a new edition`` -- the named edition does not resolve, i.e. a
  bad id at the source. The catalog falls back to ordinary matching rather than
  saving against a key that is not there.
- ``no edition resolved`` -- the record raised; read the logged exception.

Pass ``--no-expect-edition-ids`` for feeds whose ids are not OL editions; the
run then reports what was matched without claiming an expected answer.

Requires a working catalog connection, so run it where ``manage-imports`` runs.
"""

import logging
from collections import Counter

from openlibrary.bookworm import harvest
from openlibrary.bookworm.registry import FeedRegistry
from openlibrary.catalog.add_book import load
from openlibrary.config import load_config
from openlibrary.plugins.upstream.utils import setup_requests
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.bookworm.preview")

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


def main(
    ol_config: str = "/openlibrary/conf/openlibrary.yml",
    provider: str = "",
    limit: int | None = None,
    expect_edition_ids: bool = True,
    verbose: bool = False,
) -> None:
    """Report which edition the catalog would match for each of a feed's records.

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
        print("  is the bucket to act on. Do not let the feed write until it is zero.")


if __name__ == "__main__":
    FnToCLI(main).run()
