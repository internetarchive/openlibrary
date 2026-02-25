import asyncio
import datetime
import logging
from pathlib import Path

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

import infogami
from openlibrary.config import load_config
from openlibrary.utils.sentry import init_sentry
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
from scripts.solr_updater.trending_updater_daily import run_daily_update
from scripts.solr_updater.trending_updater_hourly import run_hourly_update
from scripts.solr_updater.trending_updater_init import (
    main as trending_updater_init_main,
)
from scripts.utils.scheduler import OlAsyncIOScheduler

logger = logging.getLogger("openlibrary.trending-updater")


async def main(
    ol_config: str,
    trending_offset_file: Path | None = None,
):
    """
    Useful environment variables:
    - OL_SOLR_BASE_URL: Override the Solr base URL
    - OL_SOLR_NEXT: Set to true if running with next version of Solr/schema
    """
    load_config(ol_config)
    init_sentry(getattr(infogami.config, 'sentry', {}))

    scheduler = OlAsyncIOScheduler("TRENDING-UPDATER", sentry_monitoring=True)

    # At XX:05, check the counts of reading log events, and use them to
    # update the trending count for 1) all works with a non-zero trending count
    # and 2) all  works with reading-log events in the last hour.
    scheduler.add_job(run_hourly_update, 'cron', minute=5, id='trending_updater_hourly')

    # At midnight each day, transfer the sum of the last 24 hours of trending
    # scores to the appropriate 'daily' slot for each work. This once more
    # affects: all works with a non-zero count for that day, or ones with a
    # current sum of greater than zero for those 24 hours.
    scheduler.add_job(
        run_daily_update, 'cron', hour=0, minute=0, id='trending_updater_daily'
    )

    if trending_offset_file:
        # If an offset file is specified, add an event listener to the scheduler
        # to update the offset file whenever a job is run.
        def update_offset(event):
            new_offset = datetime.datetime.now().isoformat()
            print(f"Updating {trending_offset_file} to {new_offset}")
            trending_offset_file.write_text(new_offset + '\n')

        scheduler.add_listener(update_offset, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

        # If an offset file is specified, read the ISO timestamp in it and if we're behind,
        # run the trending_updater_init script to catch up.
        # NOTE: Synchronous pathlib operations are acceptable here since this is CLI-only code
        # that runs once at startup. Use asyncio.to_thread() if this becomes a hot path.
        offset = None
        if trending_offset_file.exists() and (  # noqa: ASYNC240
            contents := trending_offset_file.read_text().strip()  # noqa: ASYNC240
        ):
            offset = datetime.datetime.fromisoformat(contents)

        logger.info(
            "Starting trending updater init with offset %s",
            offset.isoformat() if offset else "None",
        )
        trending_updater_init_main(
            ol_config,
            timestamp=offset.isoformat() if offset else None,
            dry_run=False,
            trending_offset_file=trending_offset_file,
        )

    scheduler.start()

    # Keep the script running to allow the scheduler to run jobs.
    await asyncio.Event().wait()


if __name__ == '__main__':
    try:
        FnToCLI(main).run()
    except (KeyboardInterrupt, SystemExit):
        print("Exiting trending updater script.")
