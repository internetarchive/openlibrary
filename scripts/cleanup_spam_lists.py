#!/usr/bin/env python3
"""
scripts/cleanup_spam_lists.py

One-time cleanup script for spam lists (issue #11905).
Finds all list documents whose name or description match spam words
and marks them as deleted in the database.

Our dump analysis found:
  - 254,050 total lists
  - 13,740 spam + zero-seed lists (high confidence)
  - Top spam: casino (1,163), pharma (1,173), phone scams (1,759)

Usage:
    # Preview only (safe — no changes made):
    python3 scripts/cleanup_spam_lists.py /olsystem/etc/openlibrary.yml --dry-run

    # Actually delete (requires explicit --confirm flag):
    python3 scripts/cleanup_spam_lists.py /olsystem/etc/openlibrary.yml --confirm
"""

import argparse
import re

import _init_path  # noqa: F401 Imported for its side effect of setting PYTHONPATH
import web

import infogami
from infogami.infobase.client import Site
from openlibrary.config import load_config


def get_spam_words(site: Site) -> list[str]:
    doc = site.store.get("spamwords") or {}
    return doc.get("spamwords", [])


def is_spam_list_content(name: str, description: str, spam_words: list[str]) -> bool:
    text = f"{name} {description}".lower()
    return any(re.search(w.lower(), text) for w in spam_words)


def find_spam_lists(site: Site, spam_words: list[str]) -> list[dict]:
    """Query all lists and return those matching spam words.

    Uses site.get_many() to fetch documents in batches instead of one-by-one,
    avoiding N+1 queries for large datasets (~250k lists).
    """
    spam_lists = []
    offset = 0
    batch_size = 1000
    while True:
        keys = site.things(
            {'type': '/type/list', 'limit': batch_size, 'offset': offset}
        )
        if not keys:
            break
        # Fetch all documents for this batch in a single call
        docs = site.get_many(keys)
        for doc in docs:
            if doc is None:
                continue
            name = doc.get('name') or ''
            description = str(doc.get('description') or '')
            if is_spam_list_content(name, description, spam_words):
                spam_lists.append({'key': doc.get('key'), 'name': name})
        offset += batch_size
    return spam_lists


def delete_list(site: Site, key: str) -> None:
    """Mark a list as deleted, attributed to ImportBot."""
    doc = {'key': key, 'type': {'key': '/type/delete'}}
    # Set IP so the changeset is attributed consistently (same pattern as other scripts)
    web.ctx.ip = '127.0.0.1'
    site.save(doc, action='lists', comment='Spam cleanup (#11905)')


def main():
    parser = argparse.ArgumentParser(
        description='Clean up spam lists. Defaults to dry-run mode; pass --confirm to delete.'
    )
    parser.add_argument('ol_config', help='Path to openlibrary.yml config file')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Preview what would be deleted without making changes (default)',
    )
    parser.add_argument(
        '--confirm',
        action='store_true',
        help='Actually perform deletions (required for destructive action)',
    )
    args = parser.parse_args()

    # --confirm overrides the default dry-run behaviour
    dry_run = not args.confirm

    load_config(args.ol_config)
    infogami._setup()

    site = web.ctx.site
    spam_words = get_spam_words(site)
    if not spam_words:
        print("No spam words configured. Exiting.")
        return

    if dry_run:
        print("[DRY RUN] No changes will be made. Pass --confirm to delete.")

    print(f"Scanning for spam lists using {len(spam_words)} spam words...")
    spam_lists = find_spam_lists(site, spam_words)
    print(f"Found {len(spam_lists)} spam lists.")

    for item in spam_lists:
        action = '[DRY RUN] Would delete' if dry_run else 'Deleting'
        print(f"  {action}: {item['key']} — \"{item['name']}\"")
        if not dry_run:
            delete_list(site, item['key'])

    if not dry_run:
        print(
            "Done. Re-run the Solr indexer to remove deleted lists from search results."
        )
    else:
        print("\nDry run complete. Run with --confirm to perform actual deletions.")


if __name__ == '__main__':
    main()
