#!/usr/bin/env python3
"""
Copies all patrons' preferences to the `store` tables.
"""
import argparse
import time
from pathlib import Path

import infogami
from openlibrary.accounts import RunAs
from openlibrary.accounts.model import OpenLibraryAccount
from openlibrary.config import load_config
from openlibrary.core import db


DEFAULT_CONFIG_PATH = "/opt/olsystem/etc/openlibrary.yml"
PREFERENCE_TYPE = 'preferences'


def setup(config_path):
    if not Path(config_path).exists():
        raise FileNotFoundError(f'no config file at {config_path}')
    load_config(config_path)
    infogami._setup()


def copy_preferences_to_store():
    page = 0
    while rs := _fetch_user_keys(page=page):
        page += 1
        for item in rs:
            # Get account
            key = item.get('key')
            username = key.split('/')[-1]
            ol_acct = OpenLibraryAccount.get_by_username(username)

            # Update preferences
            prefs = ol_acct.get_user().preferences()
            if not prefs.get('type', '') == PREFERENCE_TYPE:
                prefs['type'] = PREFERENCE_TYPE
                prefs['_rev'] = None

                with RunAs(username):
                    ol_acct.get_user().save_preferences(prefs, msg="Update preferences for store", use_store=True)
                    time.sleep(0.5)


def _fetch_user_keys(page=0):
    oldb = db.get_db()
    query = """
        SELECT key FROM thing WHERE type = (
            SELECT id FROM thing WHERE key = '/type/user'
        ) AND key LIKE '/people/%'
        ORDER BY id ASC LIMIT 1000
    """
    if page > 0:
        query += f' OFFSET {page * 1000}'

    return list(oldb.query(query))


def main(args):
    setup(args.config)
    copy_preferences_to_store()


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to the `openlibrary.yml` configuration file",
    )
    p.set_defaults(func=main)
    return p.parse_args()

if __name__ == '__main__':
    _args = _parse_args()
    _args.func(_args)
