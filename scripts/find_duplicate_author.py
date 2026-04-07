#!/usr/bin/env python3
"""Identify potential duplicate authors in Open Library data."""

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path


AuthorRow = tuple[str, str]
AuthorData = tuple[str, str, int, str]
DuplicateGroup = tuple[str, str, list[str]]


def extract_id_number(author_id: str) -> int | None:
    """Extract numeric portion from author ID like OL7133991A."""
    if author_id.startswith('/authors/'):
        author_id = author_id[9:]
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
        else:
            # Simplified: same name only
            if name:
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
                
                if num1 and num2 and abs(num1 - num2) == 1:
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
            writer.writerow(['author_name', 'work_title', 'duplicate_count', 'author_ids'])
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
'''
    )
    parser.add_argument(
        '--input', '-i',
        default='ids_next_to_each_other.csv',
        help='Input CSV with author IDs and names (default: ids_next_to_each_other.csv)',
    )
    parser.add_argument(
        '--matches', '-m',
        default='matching_pairs.csv',
        help='Output CSV for duplicate matches (default: matching_pairs.csv)',
    )

    args = parser.parse_args()

    process_csv_only(args.input, args.matches)


if __name__ == '__main__':
    main()
