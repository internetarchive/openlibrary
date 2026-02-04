#!/usr/bin/env python

import argparse
import datetime
import sys

import _init_path  # noqa: F401 Imported for its side effect of setting PYTHONPATH
from psycopg2 import DatabaseError

import infogami
from openlibrary.admin import stats
from openlibrary.config import load_config
from openlibrary.core import db


def setup(ol_config_path: str):
    load_config(ol_config_path)
    infogami._setup()


def gather_login_stats(since_days=30):
    since_date = datetime.datetime.now() - datetime.timedelta(days=since_days)
    date_str = since_date.strftime("%Y-%m-%d")

    # make queries for login stats
    tmp_table_query = """
        CREATE TEMPORARY TABLE recent_logins AS
        SELECT store_id
        FROM store_index
        WHERE type = 'account'
            AND name = 'last_login'
            AND value > $date
    """

    recent_logins_query = """
        SELECT COUNT(*) AS total_logins_since_date FROM recent_logins
    """

    returning_logins_query = """
        SELECT COUNT(si.store_id) AS logins_created_before_date
        FROM recent_logins rl
        INNER JOIN store_index si
            ON rl.store_id = si.store_id
        WHERE si.name = 'created_on'
            AND si.value < $date
    """
    oldb = db.get_db()
    t = oldb.transaction()
    try:
        oldb.query(tmp_table_query, vars={'date': date_str})
        recent_logins = list(oldb.query(recent_logins_query))
        returning_logins = list(
            oldb.query(returning_logins_query, vars={'date': date_str})
        )

        # write login stats to statsd
        stats.increment(
            'ol.logins.recent', n=recent_logins[0].get('total_logins_since_date')
        )
        stats.increment(
            'ol.logins.recent.returning',
            n=returning_logins[0].get('logins_created_before_date'),
        )

    except DatabaseError as e:
        print(f"An error occurred while fetching login statistics: {e}")
    finally:
        t.rollback()


def main(args):
    if args.login_stats:
        setup(args.openlibrary_config)
        gather_login_stats()
    sys.exit(
        stats.main(
            args.infobase_config,
            args.openlibrary_config,
            args.coverstore_config,
            args.number_of_days,
        )
    )


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('infobase_config')
    p.add_argument('openlibrary_config')
    p.add_argument('coverstore_config')
    p.add_argument('number_of_days')
    p.add_argument(
        "--login-stats",
        action="store_true",
        help="Gather and persist login stats",
    )

    p.set_defaults(func=main)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    args.func(args)
