"""
One-time script to fix HTML entity encoding errors in author names,
edition titles, and work titles.

Example of the problem:
    &#1057;&#1077;&#1088;&#1075;&#1077;&#1081; -> Сергей

Usage:
    Phase 1 - Scan dump and output affected keys:
    python3 scripts/migrations/fix_unicode_html_entities.py --dump ol_dump_authors_latest.txt.gz --type authors > author_keys.txt

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

import web

import infogami
from openlibrary.config import load_config
from scripts.utils.graceful_shutdown import init_signal_handler, was_shutdown_requested

# Matches:
#   &#1234;
#   &#x1A;
#   &alpha;
HTML_ENTITY_PATTERN = re.compile(
    r'&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-fA-F]{1,6});', re.IGNORECASE
)

FIELDS_BY_TYPE = {
    'authors': ['name', 'personal_name'],
    'editions': ['title', 'subtitle'],
    'works': ['title', 'subtitle'],
}

DEFAULT_CONFIG_PATH = "/olsystem/etc/openlibrary.yml"


def has_entities(value: str) -> bool:
    """Return True if the string contains HTML entities."""
    return bool(HTML_ENTITY_PATTERN.search(value))


def get_field_updates(record: dict, fields: list[str]) -> dict[str, str]:
    """
    Return only the fields that need updating.
    Ensures we don't overwrite unchanged values.
    """
    updates = {}

    for field in fields:
        if field in record and isinstance(record[field], str):
            original = record[field]

            if has_entities(original):
                fixed = html.unescape(original)

                if fixed != original:
                    updates[field] = fixed

    return updates


def process_dump(dump_path: str, record_type: str) -> None:
    """
    Scan dump file, output keys of records with HTML entity encoding errors.
    """
    fields = FIELDS_BY_TYPE[record_type]

    with gzip.open(dump_path, 'rt', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) < 5:
                continue

            key = parts[1]
            raw_json = parts[4]

            try:
                record = json.loads(raw_json)
            except json.JSONDecodeError:
                continue

            updates = get_field_updates(record, fields)

            if not updates:
                continue

            print(key)


def setup(config_path: str) -> None:
    """Set up the OL/Infogami connection."""
    init_signal_handler()
    if not Path(config_path).exists():
        raise FileNotFoundError(f'No config file found at {config_path}')
    load_config(config_path)
    infogami._setup()


def fix_records(keys_path: str, config_path: str, dry_run: bool = False) -> None:
    """
    Read keys from file, fetch each record from OL, fix HTML entities, and save.
    Resumes from last saved progress if interrupted.
    """
    setup(config_path)

    # Read all keys from the file
    with open(keys_path) as f:
        all_keys = [line.strip() for line in f if line.strip()]

    # Check for existing progress
    progress_file = Path(keys_path).with_suffix('.progress')
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
        record_type = key.split('/')[1]
        fields = FIELDS_BY_TYPE.get(record_type, [])
        updates = get_field_updates(data, fields)

        if updates and not dry_run:
            data.update(updates)
            web.ctx.site.save(
                data, comment='Fix HTML entity encoding in Unicode fields'
            )

        records_processed += 1

        # Save progress
        with open(progress_file, 'w') as f:
            f.write(str(records_processed))

    print(f"Done. Processed {records_processed} records.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Detect and fix HTML-escaped Unicode in OL dumps"
    )

    parser.add_argument('--dump', help='Path to .txt.gz dump file (Phase 1)')

    parser.add_argument(
        '--type',
        choices=['authors', 'editions', 'works'],
        help='Record type (required for Phase 1)',
    )

    parser.add_argument(
        '--keys', help='Path to keys file produced by Phase 1 (Phase 2)'
    )

    parser.add_argument(
        '--config',
        default=DEFAULT_CONFIG_PATH,
        help='Path to openlibrary.yml config file (Phase 2)',
    )

    parser.add_argument(
        '--dry-run', action='store_true', help='Preview changes without saving'
    )

    args = parser.parse_args()

    if args.dump:
        if not args.type:
            parser.error('--type is required when using --dump')
        process_dump(args.dump, args.type)
    elif args.keys:
        fix_records(args.keys, args.config, args.dry_run)
    else:
        parser.error('Either --dump or --keys is required')


if __name__ == '__main__':
    main()
