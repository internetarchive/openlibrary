#!/usr/bin/env python
"""coverstore server."""

import sys

import yaml

from openlibrary.coverstore import config
from openlibrary.utils.sentry import init_sentry

_setup_done = False


def load_config(configfile):
    with open(configfile) as in_file:
        d = yaml.safe_load(in_file)
    for k, v in d.items():
        setattr(config, k, v)


def setup(configfile: str) -> None:
    """Load config and init sentry. Idempotent: gunicorn imports the app factory
    per worker, and code.py may already have loaded the config at import time."""
    global _setup_done
    if _setup_done:
        return
    _setup_done = True

    load_config(configfile)

    sentry = init_sentry(getattr(config, "sentry", {}))
    if sentry.enabled:
        # The cover metadata still goes through web.py's db layer.
        sentry.bind_to_webpy_db()


def main(configfile, *args):
    from openlibrary.coverstore import archive

    setup(configfile)
    if "--archive" in args:
        archive.archive()
    else:
        raise SystemExit("Serving is handled by openlibrary.coverstore.asgi_app; see scripts/coverstore-server")


if __name__ == "__main__":
    main(*sys.argv[1:])
