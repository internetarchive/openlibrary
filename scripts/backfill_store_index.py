"""
Backfills new ID column in the `store_index` table.
"""

import argparse
import time

import web

from openlibrary.core import db
from openlibrary.setup import setup_for_script
from scripts.utils.graceful_shutdown import init_signal_handler, was_shutdown_requested

DEFAULT_CONFIG_PATH = "conf/openlibrary.yml"
DEFAULT_BATCH_SIZE = 20_000


def init(conf_path):
    init_signal_handler()
    setup_for_script(conf_path)
    web.ctx.ip = getattr(web.ctx, "ip", None) or "127.0.0.1"


def find_upper_bound():
    oldb = db.get_db()

    query = """
        SELECT MIN(new_id) as min from store_index
    """
    return next(iter(oldb.query(query)))["min"]


def backfill_rows(lower_bound, upper_bound):
    oldb = db.get_db()

    query = """
        UPDATE store_index SET new_id = id
        WHERE id BETWEEN $lo AND $hi AND new_id IS NULL
    """
    oldb.query(query, vars={"lo": lower_bound, "hi": upper_bound})


def main(args):
    init(args.config)

    # Find min new_id (for upper limit)
    max_upper_bound = find_upper_bound()

    # Backfill new IDs in batches
    lower_bound = 0
    while lower_bound < max_upper_bound and not was_shutdown_requested():
        start = time.perf_counter()
        backfill_rows(lower_bound, lower_bound + args.batch_size)
        lower_bound += args.batch_size
        elapsed = time.perf_counter() - start
        print(f"Chunk updated in {elapsed:.6f} seconds")


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-c", "--config", default=DEFAULT_CONFIG_PATH, help="Path to openlibrary configuration yaml")
    p.add_argument("-b", "--batch-size", default=DEFAULT_BATCH_SIZE, type=int)
    p.set_defaults(func=main)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    args.func(args)
