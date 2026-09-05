#!/usr/bin/env python3
"""
scripts/cleanup_spam_lists.py

One-time cleanup script for spam lists (issue #11905).

Scans an Open Library list data dump for spam words and marks matching
list documents as deleted. Uses the dump file instead of fetching every
list from the database, to avoid overloading site performance.

Our dump analysis found:
  - 254,050 total lists
  - 13,740 spam + zero-seed lists (high confidence)
  - Top spam: casino (1,163), pharma (1,173), phone scams (1,759)

Two-phase workflow (same pattern as scripts/migrations/fix_unicode_html_entities.py):

  Phase 1 — Scan dump, output matching keys to stdout:
      python3 scripts/cleanup_spam_lists.py --dump ol_dump_lists_latest.txt.gz > spam_keys.txt

  Phase 2 — Delete the listed records (dry-run by default):
      python3 scripts/cleanup_spam_lists.py --keys spam_keys.txt --config /olsystem/etc/openlibrary.yml --dry-run
      python3 scripts/cleanup_spam_lists.py --keys spam_keys.txt --config /olsystem/etc/openlibrary.yml
"""

import argparse
import gzip
import re
import sys

import _init_path  # noqa: F401 Imported for its side effect of setting PYTHONPATH
import web

import infogami
from openlibrary.accounts import RunAs
from openlibrary.config import load_config
from openlibrary.plugins.upstream.spamcheck import get_spam_words

DEFAULT_CONFIG_PATH = "/olsystem/etc/openlibrary.yml"


def line_matches_spam(raw_line: str, spam_words: list[str]) -> bool:
    """Return True if any spam-word regex matches anywhere in the raw dump line.

    Each entry in spam_words is a regular expression (case-sensitive,
    as stored in the spamwords document).  We avoid json.loads for
    performance — a substring match on the raw JSON line is sufficient.
    """
    return any(re.search(w, raw_line) for w in spam_words)


def process_dump(dump_path: str, spam_words: list[str]) -> None:
    """Phase 1: scan a gzipped OL list dump and print keys of spam entries.

    The dump format is tab-separated with the key in column 2 (index 1)
    and the JSON body in column 5 (index 4).  We intentionally skip
    json.loads and search the raw JSON string directly for speed.

    Args:
        dump_path: Path to the gzipped dump file (e.g. ol_dump_lists_latest.txt.gz).
        spam_words: List of regex patterns from the spamwords store.
    """
    with gzip.open(dump_path, "rt", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 5:
                continue

            key = parts[1]
            raw_json = parts[4]

            if line_matches_spam(raw_json, spam_words):
                print(key)


def delete_list(key: str) -> None:
    """Mark a list as deleted, attributed to ImportBot."""
    doc = {"key": key, "type": {"key": "/type/delete"}}
    web.ctx.ip = web.ctx.ip or "127.0.0.1"
    with RunAs("ImportBot"):
        web.ctx.site.save(doc, action="delete-list", comment="Delete suspected spam list")


def delete_spam_lists(keys_path: str, config_path: str, dry_run: bool = True) -> None:
    """Phase 2: read keys from file and delete each matching list.

    Args:
        keys_path: Path to a file of OL list keys, one per line (output of Phase 1).
        config_path: Path to the openlibrary.yml config file.
        dry_run: If True, print what would be deleted without making changes.
    """
    load_config(config_path)
    infogami._setup()

    spam_words = get_spam_words()
    if not spam_words:
        print("No spam words configured. Exiting.", file=sys.stderr)
        return

    with open(keys_path) as f:
        keys = [line.strip() for line in f if line.strip()]

    if not keys:
        print("No keys to process.", file=sys.stderr)
        return

    if dry_run:
        print("[DRY RUN] No changes will be made. Remove --dry-run to delete.", file=sys.stderr)

    print(f"Processing {len(keys)} keys...", file=sys.stderr)

    for key in keys:
        if dry_run:
            print(f"  [DRY RUN] Would delete: {key}")
        else:
            print(f"  Deleting: {key}")
            delete_list(key)

    if dry_run:
        print("\nDry run complete. Remove --dry-run to perform actual deletions.", file=sys.stderr)
    else:
        print(
            "Done. Re-run the Solr indexer to remove deleted lists from search results.",
            file=sys.stderr,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan an OL list dump for spam and delete matching records.")

    parser.add_argument(
        "--dump",
        help="Path to gzipped list dump file (Phase 1: outputs spam keys to stdout)",
    )
    parser.add_argument(
        "--keys",
        help="Path to keys file from Phase 1 (Phase 2: deletes the listed records)",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to openlibrary.yml config file (required for Phase 2)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without making changes (Phase 2 only)",
    )

    args = parser.parse_args()

    if args.dump:
        # Phase 1: scan dump — needs spam words from the live site
        load_config(args.config)
        infogami._setup()
        spam_words = get_spam_words()
        if not spam_words:
            print("No spam words configured. Exiting.", file=sys.stderr)
            sys.exit(1)
        print(f"Scanning dump with {len(spam_words)} spam words...", file=sys.stderr)
        process_dump(args.dump, spam_words)
    elif args.keys:
        # Phase 2: delete records listed in the keys file
        delete_spam_lists(args.keys, args.config, dry_run=args.dry_run)
    else:
        parser.error("Either --dump or --keys is required.")


if __name__ == "__main__":
    main()
