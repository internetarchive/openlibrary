#!/usr/bin/env python3
"""
Deletes store entries that have the type `merge-authors-debug`.

WARNING: This will delete all of the records if the `--batches` argument is excluded.
"""

import argparse
from pathlib import Path

import web

import infogami
from infogami.infobase.client import ClientException
from openlibrary.config import load_config
from scripts.utils.graceful_shutdown import init_signal_handler, was_shutdown_requested

DEFAULT_CONFIG_PATH = "/opt/olsystem/etc/openlibrary.yml"
RECORD_TYPE = "merge-authors-debug"


def setup(config_path):
    init_signal_handler()
    if not Path(config_path).exists():
        raise FileNotFoundError(f'no config file at {config_path}')
    load_config(config_path)
    infogami._setup()


def delete_records(batches):
    """
    Deletes batches of `merge-authors-debug` records.

    A batch will contain no more than 100 records.

    If `batches` is negative, it will delete all records.

    :param batches: The number of records to delete.
    :return:
    """
    while (
        not was_shutdown_requested()
        and (batches != 0)
        and (keys := web.ctx.site.store.keys(type=RECORD_TYPE))
    ):
        for key in keys:
            try:
                web.ctx.site.store.delete(key)
            except ClientException:
                print(f'Failed to delete record with key {key}\nContinuing...')
                continue
        batches -= 1


def main(args):
    setup(args.config)
    delete_records(args.batches)


def _parse_args():
    _parser = argparse.ArgumentParser(description=__doc__)
    _parser.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to the `openlibrary.yml` configuration file",
    )
    _parser.add_argument(
        "-b",
        "--batches",
        type=int,
        default=-1,
        help="Number of batches to delete (a batch contains 100 records)",
    )
    _parser.set_defaults(func=main)
    return _parser.parse_args()


if __name__ == '__main__':
    _args = _parse_args()
    _args.func(_args)
