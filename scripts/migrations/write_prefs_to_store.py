#!/usr/bin/env python3
"""
Copies all patrons' preferences to the `store` tables.
"""

import argparse
from pathlib import Path

from psycopg2 import DatabaseError

import infogami
from openlibrary.accounts import RunAs
from openlibrary.accounts.model import OpenLibraryAccount
from openlibrary.config import load_config
from openlibrary.core import db
from scripts.utils.graceful_shutdown import init_signal_handler, was_shutdown_requested

DEFAULT_CONFIG_PATH = "/olsystem/etc/openlibrary.yml"
PREFERENCE_TYPE = 'preferences'


def setup(config_path):
    init_signal_handler()
    if not Path(config_path).exists():
        raise FileNotFoundError(f'no config file at {config_path}')
    load_config(config_path)
    infogami._setup()


def copy_preferences_to_store(keys, verbose: bool = False) -> list[str]:
    errors = []
    for key in keys:
        if was_shutdown_requested():
            break
        try:
            if verbose:
                print(f"Writing {key} to store...")
            username = key.split('/')[-2]
            ol_acct = OpenLibraryAccount.get_by_username(username)
            prefs = (ol_acct and ol_acct.get_user().preferences()) or {}
            if ol_acct and prefs.get('type', '') != PREFERENCE_TYPE:
                prefs['type'] = PREFERENCE_TYPE
                prefs['_rev'] = None

                with RunAs(username):
                    ol_acct.get_user().save_preferences(prefs)
        except Exception as e:  # noqa: BLE001
            print(f"An error occurred while copying preferences to store: {e}")
            errors.append(key)

    return errors


def _fetch_preference_keys() -> list[str]:
    """
    Returns a list of all preference keys that contain a `pda` value but are
    not yet persisted in the store.

    """
    oldb = db.get_db()
    t = oldb.transaction()

    tmp_tbl_query = """
        CREATE TEMPORARY TABLE temp_preference_ids AS
        SELECT thing_id FROM datum_str
        WHERE key_id = (
            SELECT id FROM property
            WHERE name = 'notifications.pda'
        )
        ORDER BY thing_id ASC
    """

    preference_key_join_query = """
        SELECT thing.key as key FROM thing
        LEFT JOIN store ON thing.key = store.key
        WHERE thing.id IN (
            SELECT thing_id FROM temp_preference_ids
        )
        AND store.key IS NULL;
    """

    keys = []
    try:
        # Create temporary table containing `thing` IDs of all affected preference objects
        oldb.query(tmp_tbl_query)

        missing_store_entries = oldb.query(preference_key_join_query)
        keys = [entry.get('key', '') for entry in list(missing_store_entries)]
    except DatabaseError as e:
        print(f"An error occurred while fetching preference keys: {e}")
        t.rollback()
    t.rollback()
    return keys


def _fetch_legacy_preference_keys() -> list[str]:
    """
    Returns a list of preference keys that exist in the `thing`
    table, but do not exist in the `store` table.
    """
    oldb = db.get_db()

    legacy_key_query = """
        WITH preference_keys AS (
            SELECT key FROM thing
            WHERE type = (
                SELECT id FROM thing WHERE key = '/type/object'
            )
            AND key LIKE '/people/%/preferences'
            ORDER BY id DESC
        )
        SELECT t.key
        FROM preference_keys t
        LEFT JOIN store s ON t.key = s.key
        WHERE s.key IS NULL
    """

    keys = []
    try:
        legacy_preference_entries = oldb.query(legacy_key_query)
        keys = [entry.get('key', '') for entry in list(legacy_preference_entries)]
    except DatabaseError as e:
        print(f"An error occurred while fetching preference keys: {e}")

    return keys


def main(args):
    print("Setting up connection with DB...")
    setup(args.config)

    print("Fetching affected preferences...")
    affected_pref_keys = (
        _fetch_legacy_preference_keys() if args.legacy else _fetch_preference_keys()
    )

    print(f"Found {len(affected_pref_keys)} affected preferences")
    if args.dry_run:
        print("Skipping copy to store step...")
        return

    print("Copying preferences to store...")
    while affected_pref_keys and not was_shutdown_requested():
        print(
            f"Begin writing batch of {len(affected_pref_keys)} preferences to store..."
        )
        cur_batch = affected_pref_keys[:1000]
        affected_pref_keys = affected_pref_keys[1000:]
        retries = copy_preferences_to_store(cur_batch, verbose=args.verbose)
        affected_pref_keys.extend(retries)
        print(f"Batch completed with {len(retries)} errors\n")

    if was_shutdown_requested():
        print("Script terminated early due to shutdown request.")
        return

    print("All affected preferences have been written to the store.")


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to the `openlibrary.yml` configuration file",
    )
    p.add_argument(
        "--legacy",
        action="store_true",
        help="Writes all remaining legacy preferences to the store",
    )
    p.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Enable dry-run mode, which merely prints the number of preference keys that will be written to the store",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print each preference key when it is added to the store",
    )
    p.set_defaults(func=main)
    return p.parse_args()


if __name__ == '__main__':
    _args = _parse_args()
    _args.func(_args)
    print("\nScript execution complete. So long and take care!")
