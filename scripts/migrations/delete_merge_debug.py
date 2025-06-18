#!/usr/bin/env python3
"""
Deletes all store entries that have the type `merge-authors-debug`.
"""
import argparse
import web
from pathlib import Path

import infogami
from openlibrary.config import load_config

DEFAULT_CONFIG_PATH = "/opt/olsystem/etc/openlibrary.yml"
RECORD_TYPE = "merge-authors-debug"


def setup(config_path):
    if not Path(config_path).exists():
        raise FileNotFoundError(f'no config file at {config_path}')
    load_config(config_path)
    infogami._setup()


def delete_records():
    while keys := web.ctx.site.store.keys(type=RECORD_TYPE):
        for key in keys:
            web.ctx.site.store.delete(key)


def main(args):
    setup(args.config)
    delete_records()


def _parse_args():
    _parser = argparse.ArgumentParser(description=__doc__)
    _parser.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to the `openlibrary.yml` configuration file",
    )
    _parser.set_defaults(func=main)
    return _parser.parse_args()

if __name__ == '__main__':
    _args = _parse_args()
    _args.func(_args)
