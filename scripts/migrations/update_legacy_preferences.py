#!/usr/bin/env python3
"""
Updates all legacy preferences, deleting "rpd" and "pda" values.
"""

import argparse
from pathlib import Path

import web

import infogami
from openlibrary.accounts import RunAs
from openlibrary.config import load_config
from openlibrary.core import db
from scripts.utils.graceful_shutdown import init_signal_handler, was_shutdown_requested

DEFAULT_CONFIG_PATH = "/olsystem/etc/openlibrary.yml"


def setup(config_path):
    init_signal_handler()
    if not Path(config_path).exists():
        raise FileNotFoundError(f'No configuration file found at {config_path}')
    load_config(config_path)
    infogami._setup()
    web.ctx.ip = web.ctx.ip or '127.0.0.1'


def fetch_affected_keys() -> list[str]:
    oldb = db.get_db()
    thing_id_query = """
        SELECT t.key
            FROM thing t
            JOIN (
                SELECT thing_id
                    FROM datum_str
                    WHERE key_id = (SELECT id FROM property WHERE name = 'notifications.pda')
                UNION
                SELECT thing_id
                    FROM datum_int
                    WHERE key_id = (SELECT id FROM property WHERE name = 'notifications.rpd')
            ) pd_prefs ON t.id = pd_prefs.thing_id
    """

    results = list(oldb.query(thing_id_query))
    return [item.key for item in results]


def update_preferences(keys: list[str]) -> list[str]:
    retry_list = []
    for key in keys:
        try:
            prefs = web.ctx.site.get(key)
            new_prefs = prefs.dict()
            if 'pda' in new_prefs['notifications']:
                del new_prefs['notifications']['pda']
            if 'rpd' in new_prefs['notifications']:
                del new_prefs['notifications']['rpd']
            username = key.split('/')[2]
            with RunAs(username):
                web.ctx.site.save(new_prefs, 'Updating preferences')
        except (infogami.infobase.client.ClientException, KeyError, IndexError):
            retry_list.append(key)

    return retry_list


def main(args):
    print("Setting up connection with DB...")
    setup(args.config)

    print("Fetching keys of affected preference objects...")
    affected_keys = fetch_affected_keys()
    print(f"Found {len(affected_keys)} affected preference objects...")

    if args.dry_run:
        print("Skipping preference update step....")
        return

    print("Updating preferences in batches of 1,000...")
    batch_count = 1
    error_cases = []
    while affected_keys and not was_shutdown_requested():
        print(f"  Beginning batch #{batch_count}...")
        cur_batch = affected_keys[:1000]
        affected_keys = affected_keys[1000:]
        keys_to_retry = update_preferences(cur_batch)
        error_cases.extend(keys_to_retry)
        batch_count += 1
        print(f"{len(keys_to_retry)} keys have been added to the retry queue.")

    print("\nAll keys processed")
    print(f"{len(error_cases)} key(s) could not be updated.")
    for key in error_cases:
        print(key)
    if was_shutdown_requested():
        print("Script terminated early due to shutdown request")
        return


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to the `openlibrary.yml` configuration file",
    )
    p.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Enable dry-run mode, which merely prints the number of preference keys that will be written to the store",
    )

    p.set_defaults(func=main)
    return p.parse_args()


if __name__ == "__main__":
    _args = _parse_args()
    _args.func(_args)
    print("\nScript execution complete.  Have a good day!")
