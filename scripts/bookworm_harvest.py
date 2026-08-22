#!/usr/bin/env python
"""BookWorm feed-harvest cron entrypoint (#12844).

Runs ONE harvest cycle over every registered feed: fetch each feed, parse its
publications into Open Library import records (carrying ``acquisitions[]``), and
submit them to the ``import_item`` queue. ImportBot (``manage-imports
import-all``) then loads them and the catalog writes the acquisitions.

This is the v1 runner: a periodic cron on the ol-home0 cron container, e.g.

    OL_CONFIG=/olsystem/etc/openlibrary.yml \
        python scripts/bookworm_harvest.py

Scheduling is the crontab's job (hourly in prod), so this exits after one pass
rather than looping. A long-running FastAPI packaging of the same
``harvest_all`` is a later step; the harvest logic lives in
``openlibrary/bookworm/harvest.py`` either way.
"""

import logging
import os
import sys

from openlibrary.bookworm import harvest
from openlibrary.config import load_config

logger = logging.getLogger("openlibrary.bookworm.cron")


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    load_config(os.environ.get("OL_CONFIG", "/openlibrary/conf/openlibrary.yml"))
    results = harvest.harvest_all()
    logger.info("bookworm harvest complete: %s", results)
    # Non-zero exit if every feed errored, so cron surfaces a total failure.
    return 1 if results and all(r.get("error") for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
