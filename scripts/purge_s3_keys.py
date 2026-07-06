#!/usr/bin/env python3
"""Remove plaintext S3 keys from all account store objects.

DO NOT RUN until all production sessions have been migrated to cookie-based
S3 key storage (i.e., after the cookie infrastructure has been live long
enough that no active sessions rely on the store fallback).

Usage (from within the running web container):
    python scripts/purge_s3_keys.py [--dry-run]

With --dry-run, prints accounts that would be modified without writing.
"""

import argparse
import sys

import web


def purge_s3_keys(dry_run: bool = False) -> None:
    modified = 0
    skipped = 0

    for doc in web.ctx.site.store.values(type="account"):
        if "s3_keys" not in doc:
            skipped += 1
            continue
        key = doc["_key"]
        if dry_run:
            print(f"[dry-run] would remove s3_keys from {key}")
        else:
            del doc["s3_keys"]
            web.ctx.site.store[key] = doc
            print(f"removed s3_keys from {key}")
        modified += 1

    print(f"\nDone: {modified} modified, {skipped} skipped (no s3_keys).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print accounts without writing")
    args = parser.parse_args()
    purge_s3_keys(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
