#!/usr/bin/env python3
"""
Identifies and deletes any remaining `account-email` store entries that are associated
with anonymized accounts.
"""

import argparse
from pathlib import Path

import web

import infogami
from openlibrary.config import load_config
from openlibrary.core import db

DEFAULT_CONFIG_PATH = "/olsystem/etc/openlibrary.yml"


def setup(config_path):
    if not Path(config_path).exists():
        raise FileNotFoundError(f'no config file at {config_path}')

    load_config(config_path)
    infogami._setup()


def remediate(test=False):
    def fetch_usernames():
        oldb = db.get_db()

        query = """
            SELECT SUBSTRING(key FROM 9) as username from thing
            WHERE type IN (SELECT id FROM thing WHERE key = '/type/delete' LIMIT 1)
            AND key LIKE '/people/%'
            AND LENGTH(key) - LENGTH(REPLACE(key, '/', '')) = 2
            ORDER BY id ASC
            """

        return list(oldb.query(query))

    def fetch_store_key(_username):
        oldb = db.get_db()
        data = {
            'username': _username,
        }
        query = """
            SELECT s2.value as key_value
            FROM store_index s1
            JOIN store_index s2
              ON s1.store_id = s2.store_id
            WHERE s1.type = 'account-email'
              AND s1.name = 'username'
              AND s1.value = $username
              AND s2.type = 'account-email'
              AND s2.name = '_key'
            """

        result = list(oldb.query(query, vars=data))
        return (result and result[0]['key_value']) or ''

    def is_account_active(store_key: str) -> bool:
        """
        Returns `True` if there is a store entry associated with `store_key`.
        """
        oldb = db.get_db()
        data = {
            'key': store_key,
        }
        query = "SELECT id FROM store WHERE key = $key"
        result = list(oldb.query(query, vars=data))
        return bool(result)

    deleted_entries = 0
    usernames = fetch_usernames()

    for record in usernames:
        if not is_account_active(f"account/{record['username']}") and (
            key := fetch_store_key(record['username'])
        ):
            print(f"Found affected record with key: {key}")
            if not test:
                web.ctx.site.store.delete(key)
            deleted_entries += 1

    print(f"Remediated {deleted_entries} `account-email` store entries.")


def main(args):
    setup(args.config)
    remediate(args.test)


def _parse_args():
    _parser = argparse.ArgumentParser(description=__doc__)
    _parser.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to the `openlibrary.yml` configuration file",
    )
    _parser.add_argument(
        "-t",
        "--test",
        action="store_true",
        help="Runs the script without deleting any entries",
    )
    _parser.set_defaults(func=main)
    return _parser.parse_args()


if __name__ == '__main__':
    _args = _parse_args()
    _args.func(_args)
