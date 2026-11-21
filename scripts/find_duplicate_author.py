#!/usr/bin/env python3
"""Identify potential duplicate authors in Open Library data."""

__author__ = 'Maifee Ul Asad'

import argparse
import csv
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

AuthorRow = tuple[str, str]
AuthorData = tuple[str, str, int, str]
DuplicateGroup = tuple[str, str, list[str]]


def extract_id_number(author_id: str) -> int | None:
    """Extract numeric portion from author ID like OL7133991A."""
    author_id = author_id.removeprefix('/authors/')
    match = re.search(r'OL(\d+)', author_id)
    return int(match.group(1)) if match else None


def load_author_ids_from_csv(csv_path: str | Path) -> list[AuthorRow]:
    """Load author IDs and names from the CSV file."""
    authors: list[AuthorRow] = []
    with Path(csv_path).open('r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 2:
                authors.append((row[0].strip(), row[1].strip()))
    return authors


def load_dump_file(dump_path: str | Path, key_prefix: str) -> dict[str, dict]:
    """Load records from an Open Library JSON-lines dump file, keyed by id."""
    records: dict[str, dict] = {}
    dump_path = Path(dump_path)
    opener = gzip.open if dump_path.suffix == '.gz' else open

    with opener(dump_path, 'rt', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            record_id = record.get('key', '').replace(key_prefix, '')
            if record_id:
                records[record_id] = record

    return records


def get_author_work_info(
    author_id: str,
    authors_db: dict[str, dict],
    works_db: dict[str, dict],
) -> tuple[int, str]:
    """Get work count and the title of the first work for an author."""
    works = authors_db.get(author_id, {}).get('works', [])
    if not works:
        return 0, ''

    first_work = works[0]
    if isinstance(first_work, dict):
        return len(works), first_work.get('title', '')
    if isinstance(first_work, str):
        work_id = first_work.removeprefix('/works/')
        return len(works), works_db.get(work_id, {}).get('title', '')

    return len(works), ''


def find_duplicate_chains(
    authors_data: list[AuthorData],
    use_title_matching: bool,
) -> list[DuplicateGroup]:
    """
    Find chains of duplicate authors.

    Args:
        authors_data: List of (author_id, name, work_count, work_title)
        use_title_matching: If True, require matching work titles; if False, match on name only

    Returns:
        List of (name, title, [author_ids]) tuples for each duplicate chain
    """
    # Group authors by matching criteria
    groups: defaultdict[tuple[str, str], list[str]] = defaultdict(list)

    for author_id, name, work_count, work_title in authors_data:
        if use_title_matching:
            # Full matching: same name + same title + exactly 1 work
            if work_count == 1 and work_title:
                key = (name, work_title.lower().strip())
                groups[key].append(author_id)
        # Simplified: same name only
        elif name:
            key = (name, '')
            groups[key].append(author_id)

    matches: list[DuplicateGroup] = []

    for (name, title), ids in groups.items():
        if len(ids) < 2:
            continue

        sorted_ids = sorted(ids, key=lambda x: extract_id_number(x) or 0)

        # Find consecutive chains
        i = 0
        while i < len(sorted_ids):
            chain = [sorted_ids[i]]

            while i + 1 < len(sorted_ids):
                num1 = extract_id_number(sorted_ids[i])
                num2 = extract_id_number(sorted_ids[i + 1])

                if num1 is not None and num2 is not None and num2 - num1 == 1:
                    chain.append(sorted_ids[i + 1])
                    i += 1
                else:
                    break

            if len(chain) >= 2:
                matches.append((name, title, chain))

            i += 1

    return matches


def write_matches(
    matches: list[DuplicateGroup],
    matches_path: str | Path,
    include_titles: bool,
) -> None:
    """Write duplicate groups to a CSV file."""
    with Path(matches_path).open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if include_titles:
            writer.writerow(
                ['author_name', 'work_title', 'duplicate_count', 'author_ids']
            )
            for name, title, chain in matches:
                writer.writerow([name, title, len(chain), '|'.join(chain)])
        else:
            writer.writerow(['author_name', 'duplicate_count', 'author_ids'])
            for name, _, chain in matches:
                writer.writerow([name, len(chain), '|'.join(chain)])


def process_csv_only(csv_path: str | Path, matches_path: str | Path) -> None:
    """Process using only CSV data (name + consecutive ID matching)."""
    print("Loading author IDs from CSV...")
    authors = load_author_ids_from_csv(csv_path)
    print(f"Loaded {len(authors)} author records")

    # Build data without work info
    authors_data: list[AuthorData] = [(aid, name, 0, '') for aid, name in authors]

    # Find duplicates (name-only matching)
    matches = find_duplicate_chains(authors_data, use_title_matching=False)

    # Write matches
    print(f"Writing matches to {matches_path}...")
    write_matches(matches, matches_path, include_titles=False)

    total_authors = sum(len(chain) for _, _, chain in matches)
    print(f"\nFound {len(matches)} duplicate groups ({total_authors} total authors)")


def process_with_dumps(
    csv_path: str | Path,
    matches_path: str | Path,
    author_dump: str | Path,
    work_dump: str | Path,
) -> None:
    """Process authors using Open Library data dumps for work count/title info."""
    print("Loading author IDs from CSV...")
    authors = load_author_ids_from_csv(csv_path)
    print(f"Loaded {len(authors)} author records")

    print("Loading data dumps...")
    authors_db = load_dump_file(author_dump, '/authors/')
    works_db = load_dump_file(work_dump, '/works/')
    print(f"Loaded {len(authors_db)} authors and {len(works_db)} works from dumps")

    authors_data: list[AuthorData] = []
    for author_id, name in authors:
        clean_id = author_id.removeprefix('/authors/')
        work_count, work_title = get_author_work_info(clean_id, authors_db, works_db)
        authors_data.append((author_id, name, work_count, work_title))

    # Find duplicates (name + matching work title + consecutive IDs)
    matches = find_duplicate_chains(authors_data, use_title_matching=True)

    # Write matches
    print(f"Writing matches to {matches_path}...")
    write_matches(matches, matches_path, include_titles=True)

    total_authors = sum(len(chain) for _, _, chain in matches)
    print(f"\nFound {len(matches)} duplicate groups ({total_authors} total authors)")


def main():
    parser = argparse.ArgumentParser(
        description='Find duplicate authors in Open Library data.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Simplified matching (name + consecutive IDs only):
    python3 scripts/find_duplicate_author.py
    or
    python3 scripts/find_duplicate_author.py --input ids_next_to_each_other.csv --matches matching_pairs.csv

  # Full matching (name + matching work title + consecutive IDs), using data dumps:
    python3 scripts/find_duplicate_author.py --author-dump authors.json.gz --work-dump works.json.gz
''',
    )
    parser.add_argument(
        '--input',
        '-i',
        default='ids_next_to_each_other.csv',
        help='Input CSV with author IDs and names (default: ids_next_to_each_other.csv)',
    )
    parser.add_argument(
        '--matches',
        '-m',
        default='matching_pairs.csv',
        help='Output CSV for duplicate matches (default: matching_pairs.csv)',
    )
    parser.add_argument(
        '--author-dump',
        help='Path to an Open Library author dump file (JSON lines, optionally gzipped)',
    )
    parser.add_argument(
        '--work-dump',
        help='Path to an Open Library work dump file (JSON lines, optionally gzipped)',
    )

    args = parser.parse_args()

    if args.author_dump and args.work_dump:
        process_with_dumps(args.input, args.matches, args.author_dump, args.work_dump)
    else:
        process_csv_only(args.input, args.matches)


if __name__ == '__main__':
    main()
