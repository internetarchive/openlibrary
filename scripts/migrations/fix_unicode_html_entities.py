"""
One-time script to fix HTML entity encoding errors in author names,
edition titles, and work titles.

Example of the problem:
    &#1057;&#1077;&#1088;&#1075;&#1077;&#1081; -> Сергей

Usage:
    python3 scripts/migrations/fix_unicode_html_entities.py --dump ol_dump_authors_latest.txt.gz --type authors --dry-run
    python3 scripts/migrations/fix_unicode_html_entities.py --dump ol_dump_editions_latest.txt.gz --type editions --dry-run
"""

import argparse
import gzip
import html
import json
import re

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


def process_dump(dump_path: str, record_type: str, dry_run: bool = True):
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


def main():
    parser = argparse.ArgumentParser(
        description="Detect and fix HTML-escaped Unicode in OL dumps"
    )

    parser.add_argument('--dump', required=True, help='Path to .txt.gz dump file')

    parser.add_argument(
        '--type',
        required=True,
        choices=['authors', 'editions', 'works'],
        help='Record type',
    )

    parser.add_argument(
        '--dry-run', action='store_true', help='Preview changes (default behavior)'
    )

    args = parser.parse_args()

    process_dump(
        dump_path=args.dump,
        record_type=args.type,
        dry_run=args.dry_run,
    )

if __name__ == '__main__':
    main()
