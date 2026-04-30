#!/usr/bin/env python3
"""
One-time script to fix HTML entity encoding errors in Open Library records.

Example of the problem:
    &#1057;&#1077;&#1088;&#1075;&#1077;&#1081; -> Сергей

Usage:
    Phase 1 - Scan dump and output affected keys:
    python3 scripts/migrations/fix_unicode_html_entities.py --dump ol_dump_authors_latest.txt.gz > author_keys.txt

    Phase 2 - Fetch, fix, and save records:
    python3 scripts/migrations/fix_unicode_html_entities.py --keys author_keys.txt --config /path/to/openlibrary.yml
"""

import argparse
import gzip
import html
import json
import re
import sys
from pathlib import Path

import infogami
import web

from openlibrary.accounts import RunAs
from openlibrary.config import load_config
from scripts.utils.graceful_shutdown import init_signal_handler, was_shutdown_requested

# Matches:
#   &#1234;
#   &#x1A;
#   &alpha;
HTML_ENTITY_PATTERN = re.compile(r"&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-fA-F]{1,6});", re.IGNORECASE)

DEFAULT_CONFIG_PATH = "/olsystem/etc/openlibrary.yml"


def has_entities(value: str) -> bool:
    """Return True if the string contains HTML entities."""
    return bool(HTML_ENTITY_PATTERN.search(value))


def get_field_updates(record: dict) -> dict:
    """
    Return only the fields that contain HTML entities, with entities fixed.
    Checks all string fields rather than a fixed list.
    Handles fields that can be a plain string, an object with a value
    property, or a list of such objects.
    """
    updates: dict[str, str | dict | list] = {}
    for key, value in record.items():
        if isinstance(value, str) and has_entities(value):
            fixed = html.unescape(value)
            if fixed != value:
                updates[key] = fixed
        elif isinstance(value, dict) and has_entities(value.get("value", "")):
            fixed = html.unescape(value["value"])
            if fixed != value["value"]:
                updates[key] = {**value, "value": fixed}
        elif isinstance(value, list):
            fixed_list = []
            changed = False
            for item in value:
                if isinstance(item, dict) and has_entities(item.get("value", "")):
                    fixed_item = html.unescape(item["value"])
                    if fixed_item != item["value"]:
                        fixed_list.append({**item, "value": fixed_item})
                        changed = True
                        continue
                fixed_list.append(item)
            if changed:
                updates[key] = fixed_list
    return updates


def process_dump(dump_path: str) -> None:
    """
    Scan a gzipped OL dump file and print keys of records that contain
    HTML entity encoding errors, one key per line.

    Args:
        dump_path: Path to a gzipped tab-separated OL dump file (.txt.gz).
    """
    with gzip.open(dump_path, "rt", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 5:
                continue

            key = parts[1]
            raw_json = parts[4]

            if not has_entities(raw_json):
                continue

            try:
                record = json.loads(raw_json)
            except json.JSONDecodeError:
                continue

            updates = get_field_updates(record)

            if not updates:
                continue

            print(key)


def setup(config_path: str) -> None:
    """
    Initialize the Infogami/OL environment required for database access.
    Loads config, sets up the web.ctx.site connection, and registers
    a graceful shutdown signal handler.

    Args:
        config_path: Path to the openlibrary.yml config file.

    Raises:
        FileNotFoundError: If the config file does not exist.
    """
    init_signal_handler()
    if not Path(config_path).exists():
        raise FileNotFoundError(f"No config file found at {config_path}")
    load_config(config_path)
    infogami._setup()


def fix_records(keys_path: str, config_path: str, dry_run: bool = False) -> None:
    """
    Read record keys from a file, fetch each from the OL database, fix
    any HTML entity encoding errors, and save the updated record.

    Supports resuming from the last saved position if interrupted. Progress
    is tracked in a .progress file alongside the keys file.

    Args:
        keys_path: Path to a file containing one OL key per line.
        config_path: Path to the openlibrary.yml config file.
        dry_run: If True, detect and log changes without saving.
    """
    setup(config_path)

    # Read all keys from the file
    with open(keys_path) as f:
        all_keys = [line.strip() for line in f if line.strip()]

    # Check for existing progress
    progress_file = Path(keys_path).with_suffix(".progress")
    offset = 0
    if progress_file.exists():
        with open(progress_file) as f:
            offset = int(f.read().strip())
        print(f"Resuming from record {offset}", file=sys.stderr)

    keys_to_process = all_keys[offset:]
    records_processed = offset

    for key in keys_to_process:
        if was_shutdown_requested():
            print(
                f"Shutdown requested. Stopped at record {records_processed}.",
                file=sys.stderr,
            )
            break

        record = web.ctx.site.get(key)
        if record is None:
            print(f"Record not found: {key}", file=sys.stderr)
            records_processed += 1
            continue

        data = record.dict()
        updates = get_field_updates(data)

        if updates and not dry_run:
            data.update(updates)
            with RunAs("ImportBot"):
                web.ctx.site.save(data, comment="Decode HTML entity encoding", action="update")

        records_processed += 1

        # Save progress
        with open(progress_file, "w") as f:
            f.write(str(records_processed))

    print(f"Done. Processed {records_processed} records.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Detect and fix HTML-escaped Unicode in OL dumps")

    parser.add_argument("--dump", help="Path to .txt.gz dump file (Phase 1)")

    parser.add_argument("--keys", help="Path to keys file produced by Phase 1 (Phase 2)")

    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to openlibrary.yml config file (Phase 2)",
    )

    parser.add_argument("--dry-run", action="store_true", help="Preview changes without saving")

    args = parser.parse_args()

    if args.dump:
        process_dump(args.dump)
    elif args.keys:
        fix_records(args.keys, args.config, args.dry_run)
    else:
        parser.error("Either --dump or --keys is required")


if __name__ == "__main__":
    main()
