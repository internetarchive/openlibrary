import datetime
from pathlib import Path

from openlibrary.config import load_config
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
from scripts.solr_updater.trending_updater_daily import run_daily_update
from scripts.solr_updater.trending_updater_hourly import run_hourly_update


def main(
    openlibrary_yml: str,
    timestamp: str | None = None,
    dry_run: bool = False,
    trending_offset_file: Path | None = None,
    allow_old_timestamp: bool = False,
):
    """
    Script to initialize the trending data in Solr.

    Environment variables:

        OL_SOLR_BASE_URL: The base URL for the Solr instance.

    To run over the last 7 days:

        PYTHONPATH=. python scripts/solr_updater/trending_updater_init.py /olsystem/etc/openlibrary.yml

    To run starting from a specific timestamp to present:

        PYTHONPATH=. python scripts/solr_updater/trending_updater_init.py /olsystem/etc/openlibrary.yml --timestamp 2025-06-24T00:05:00

    :param openlibrary_yml: Path to the Open Library configuration file.
    :param timestamp: Optional ISO format timestamp to start from. Default is 7 days ago.
    :param dry_run: If True, will not send updates to Solr, just runs the logic and print the number of updates.
    """
    load_config(openlibrary_yml)

    min_start = datetime.datetime.now() - datetime.timedelta(days=7)
    # Ensure we start at the beginning of the day
    min_start = min_start.replace(hour=0, minute=5, second=0, microsecond=0)

    if timestamp:
        start = datetime.datetime.fromisoformat(timestamp)
        start = start.replace(minute=5, second=0, microsecond=0)
        if not allow_old_timestamp and start < min_start:
            print(
                f"Timestamp {start.isoformat()} older than 7 days ago, using {min_start.isoformat()} instead."
            )
            start = min_start
    else:
        start = min_start

    cur_dt = start
    while cur_dt < datetime.datetime.now():
        # After 24 hours, run daily trending for this day
        if cur_dt.hour == 0:
            day_dt = cur_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            print(f"Running daily trending for {day_dt.isoformat()}")
            run_daily_update(timestamp=day_dt.isoformat(), dry_run=dry_run)
            if not dry_run and trending_offset_file:
                trending_offset_file.write_text(day_dt.isoformat() + '\n')

        print(f"Running hourly trending for {cur_dt.isoformat()}")
        run_hourly_update(timestamp=cur_dt.isoformat(), dry_run=dry_run)
        if not dry_run and trending_offset_file:
            trending_offset_file.write_text(cur_dt.isoformat() + '\n')

        cur_dt += datetime.timedelta(hours=1)

    print("Caught up to current time, stopping.")


if __name__ == '__main__':
    FnToCLI(main).run()
