"""
One-time script to fix HTML entity encoding errors in author names,
edition titles, and work titles.

Example of the problem:
    &#1057;&#1077;&#1088;&#1075;&#1077;&#1081; -> Сергей

Usage:
    python3 scripts/fix_unicode_html_entities.py --dump ol_dump_authors_latest.txt.gz --type authors --dry-run
    python3 scripts/fix_unicode_html_entities.py --dump ol_dump_editions_latest.txt.gz --type editions --dry-run
"""

import argparse
import gzip
import html
import json
import re
from typing import Tuple, Dict, List


# Matches:
#   &#1234;
#   &#x1A;
#   &alpha;
HTML_ENTITY_PATTERN = re.compile(
    r'&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-fA-F]{1,6});',
    re.IGNORECASE
)


FIELDS_BY_TYPE = {
    'authors':  ['name', 'personal_name'],
    'editions': ['title', 'subtitle'],
    'works':    ['title', 'subtitle'],
}


def has_entities(value: str) -> bool:
    """Return True if the string contains HTML entities."""
    return bool(HTML_ENTITY_PATTERN.search(value))


def get_field_updates(record: Dict, fields: List[str]) -> Dict[str, str]:
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


def process_dump(
    dump_path: str,
    record_type: str,
    dry_run: bool = True,
    limit: int = None
):
    """
    Scan dump file, detect broken records, and optionally preview fixes.
    """
    fields = FIELDS_BY_TYPE[record_type]

    total = 0
    broken = 0

    print(f"Processing: {dump_path}")
    print(f"Record type: {record_type}")
    print(f"Dry run: {dry_run}")
    print(f"Fields: {fields}")
    print("-" * 60)

    with gzip.open(dump_path, 'rt', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) < 5:
                continue

            total += 1
            key = parts[1]
            raw_json = parts[4]

            try:
                record = json.loads(raw_json)
            except json.JSONDecodeError:
                continue

            updates = get_field_updates(record, fields)

            if not updates:
                continue

            broken += 1

            # Show preview
            print(f"KEY:   {key}")
            for field, new_value in updates.items():
                print(f"FIELD:  {field}")
                print(f"BEFORE: {record[field]}")
                print(f"AFTER:  {new_value}")
            print("-" * 60)

            # Limit output for readability
            if limit and broken >= limit:
                print(f"\nStopping early at {limit} broken records.")
                break

    print("\nSummary:")
    print(f"  Total scanned: {total}")
    print(f"  Broken found:  {broken}")


def main():
    parser = argparse.ArgumentParser(
        description="Detect and fix HTML-escaped Unicode in OL dumps"
    )

    parser.add_argument(
        '--dump',
        required=True,
        help='Path to .txt.gz dump file'
    )

    parser.add_argument(
        '--type',
        required=True,
        choices=['authors', 'editions', 'works'],
        help='Record type'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes (default behavior)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=20,
        help='Limit number of broken records to display (default: 20)'
    )

    args = parser.parse_args()

    process_dump(
        dump_path=args.dump,
        record_type=args.type,
        dry_run=args.dry_run,
        limit=args.limit
    )

# ------------------------------------------------------------
# FUTURE WORK (These will be decided during PR Discussion)
# ------------------------------------------------------------
# - Batch keys (~1000)
# - Fetch via web.ctx.site.get_many(keys)
# - Apply updates from get_field_updates()
# - Save via save_many(...) or per-record commits
# ------------------------------------------------------------
if __name__ == '__main__':
    main()