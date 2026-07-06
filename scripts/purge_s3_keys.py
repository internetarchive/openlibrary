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
import json
import sys

from psycopg2 import DatabaseError

from openlibrary.core import db
from openlibrary.setup import setup_for_script
from scripts.utils.graceful_shutdown import init_signal_handler, was_shutdown_requested


DEFAULT_CONFIG_PATH = "/olsystem/etc/openlibrary.yml"

def setup(config_path=DEFAULT_CONFIG_PATH):
    setup_for_script(config_path)
    init_signal_handler()

def get_all_affected_keys():
    query = """
        SELECT key FROM store
        WHERE id IN (
            SELECT store_id FROM store_index
            WHERE type = 'account'
                AND name = 's3_keys.access'
        )
    """
    oldb = db.get_db()
    rs = oldb.query(query)
    return iter(rs)

def get_affected_keys_batch(limit=100_000):
    query = """
        SELECT key FROM store
        WHERE id IN (
            SELECT store_id FROM store_index
            WHERE type = 'account'
                AND name = 's3_keys.access'
            LIMIT $limit
        )
    """
    oldb = db.get_db()
    rs = oldb.query(query, vars={"limit": limit})
    return iter(rs)

def update_record(key: str) -> bool:
    acct_rec_query = "SELECT id, json FROM store WHERE key = $key"
    acct_rec_update_query = "UPDATE store SET json = $json WHERE key = $key"
    store_index_delete_query = """
       DELETE FROM store_index
       WHERE
           store_id = $store_id 
           AND name IN ('s3_keys.access', 's3_keys.secret')
   """

    oldb = db.get_db()
    t = oldb.transaction()
    try:
        # Fetch account record:
        rs = oldb.query(acct_rec_query, vars={"key": key})
        result = next(iter(rs))
        acct_rec_json = result.get('json')
        store_id = result.get('id')

        # Update account record
        acct_rec = json.loads(acct_rec_json)
        if 's3_keys' in acct_rec:
            del acct_rec['s3_keys']
        oldb.query(
            acct_rec_update_query,
            vars={"key": key, "json": json.dumps(acct_rec)}
        )

        # Delete keys from store_index
        oldb.query(store_index_delete_query, vars={"store_id": store_id})
        t.commit()
    except DatabaseError as e:
        t.rollback()
        return False

    return True

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print accounts without writing")
    args = parser.parse_args()

    setup()

    if args.dry_run:
        it = get_all_affected_keys()
        for record in it:
            print(record["key"])
            if was_shutdown_requested():
                return 130
    else:
        while (it := get_affected_keys_batch()) and len(it):
            for record in it:
                key = record["key"]
                success = update_record(key)
                if not success:
                    print(f"Failed to update {key}")
                if was_shutdown_requested():
                    return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
