#!/usr/bin/env python3
"""BookWorm feed-ingestion cron entrypoint (#12655 / #12844).

Runs the staging pipeline — harvest registered feeds into the ``tbp_staged_record``
buffer, then promote staged records into the import queue — once or on a loop.
This is the command the ``bookworm`` container runs; it also runs on dev.

DB routing: in production/dev the bookworm service should point its DB connection
at the isolated ``staging-db`` (via ``conf/openlibrary.yml`` / ``db_parameters``),
so bulk harvesting never contends with the production Open Library database.
"""

from __future__ import annotations

import logging
import time

try:
    import _init_path  # type: ignore[import-not-found]  # noqa: F401 side effect: add OL package root to sys.path
except ImportError:
    import scripts._init_path  # noqa: F401 same side effect when imported as a package

from openlibrary.config import load_config
from openlibrary.core import bookworm
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.bookworm.cron")


def main(ol_config: str, once: bool = False, interval: int = 3600, max_pages: int | None = None) -> None:
    """Run the bookworm staging pipeline.

    :param ol_config: Path to ``openlibrary.yml`` (should point db at staging-db).
    :param once: Run a single cycle and exit, instead of looping.
    :param interval: Seconds to sleep between cycles when looping.
    :param max_pages: Optional cap on pagination depth per feed.
    """
    load_config(ol_config)
    while True:
        summary = bookworm.run_once(max_pages=max_pages)
        logger.info("bookworm cycle: %s", summary)
        if once:
            return
        time.sleep(interval)


if __name__ == "__main__":
    FnToCLI(main).run()
