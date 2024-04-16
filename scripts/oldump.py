#!/usr/bin/env python

import logging
import os
import sys
from datetime import datetime

import _init_path  # Imported for its side effect of setting PYTHONPATH

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)


def log(*args) -> None:
    args_str = " ".join(str(a) for a in args)
    msg = f"{datetime.now():%Y-%m-%d %H:%M:%S} [openlibrary.dump] {args_str}"
    logger.info(msg)
    print(msg, file=sys.stderr)


if __name__ == "__main__":
    from contextlib import redirect_stdout
    from openlibrary.config import load_config
    from openlibrary.data import dump
    from openlibrary.utils.sentry import sentry_factory

    log("{} on Python {}.{}.{}".format(sys.argv, *sys.version_info))  # Python 3.12.2

    logger.info("Getting Sentry instance")
    sentry = sentry_factory.get_instance('ol_cron_jobs')

    log(f"sentry.enabled = {bool(sentry and sentry.enabled)}")

    dump.main(sys.argv[1], sys.argv[2:])
