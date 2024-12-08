#!/usr/bin/env python

import logging
import os
import sys
from datetime import datetime

import _init_path  # noqa: F401 Imported for its side effect of setting PYTHONPATH

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)


def log(*args) -> None:
    args_str = " ".join(str(a) for a in args)
    msg = f"{datetime.now():%Y-%m-%d %H:%M:%S} [openlibrary.dump] {args_str}"
    logger.info(msg)
    print(msg, file=sys.stderr)


if __name__ == "__main__":
    from contextlib import redirect_stdout

    from infogami import config
    from openlibrary.config import load_config
    from openlibrary.data import dump
    from openlibrary.utils.sentry import Sentry

    log("{} on Python {}.{}.{}".format(sys.argv, *sys.version_info))  # Python 3.12.2

    ol_config = os.getenv("OL_CONFIG")
    if ol_config:
        logger.info(f"loading config from {ol_config}")
        # Squelch output from infobase (needed for sentry setup)
        # So it doesn't end up in our data dumps body
        with open(os.devnull, 'w') as devnull, redirect_stdout(devnull):
            load_config(ol_config)
        sentry = Sentry(getattr(config, "sentry_cron_jobs", {}))
        if sentry.enabled:
            sentry.init()
    log(f"sentry.enabled = {bool(ol_config and sentry.enabled)}")

    dump.main(sys.argv[1], sys.argv[2:])
