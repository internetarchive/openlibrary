#!/usr/bin/env python3
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
DEFAULT_LOWER_BOUND = 0
DEFAULT_WAL_DIR_MAX_SIZE = 0


def init(conf_path):
    init_signal_handler()
    setup_for_script(conf_path)
    web.ctx.ip = getattr(web.ctx, "ip", None) or "127.0.0.1"


def find_upper_bound():
    oldb = db.get_db()

    query = """
        SELECT MAX(id) as ubound from store_index WHERE new_id IS NULL
    """
    return next(iter(oldb.query(query)))["ubound"]


def get_wal_dir_size():
    oldb = db.get_db()

    query = """
        SELECT count(*) AS file_count,
            sum(size) AS total_bytes
        FROM pg_ls_waldir();
    """
    return next(iter(oldb.query(query)))["total_bytes"]


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
    lower_bound = args.lower_bound
    iterations = 0
    while lower_bound < max_upper_bound and not was_shutdown_requested():
        if iterations % 10 == 0 and args.wal_threshold:  # noqa: SIM102
            if args.wal_threshold * (1024**3) < get_wal_dir_size():
                print("WAL directory has grown larger than threshold.  Stopping script.", flush=True)
                break
        start = time.perf_counter()
        backfill_rows(lower_bound, lower_bound + args.batch_size)
        lower_bound += args.batch_size
        elapsed = time.perf_counter() - start
        print(f"Block updated in {elapsed:.6f} seconds.  Next block starts with ID {lower_bound}", flush=True)
        iterations += 1


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-c", "--config", default=DEFAULT_CONFIG_PATH, help="Path to openlibrary configuration yaml")
    p.add_argument("-b", "--batch-size", default=DEFAULT_BATCH_SIZE, type=int)
    p.add_argument("-l", "--lower-bound", default=DEFAULT_LOWER_BOUND, type=int)
    p.add_argument(
        "-t",
        "--wal-threshold",
        default=DEFAULT_WAL_DIR_MAX_SIZE,
        type=float,
        help="If non-zero, the script will stop if the WAL directory grows beyond this many GB",
    )
    p.set_defaults(func=main)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    args.func(args)
