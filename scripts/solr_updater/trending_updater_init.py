import datetime

from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
from scripts.solr_updater.trending_updater_daily import main as daily_main
from scripts.solr_updater.trending_updater_hourly import main as hourly_main


def main(
    openlibrary_yml: str,
    timestamp: str | None = None,
    dry_run: bool = False,
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
    end = datetime.datetime.now()
    if timestamp:
        start = datetime.datetime.fromisoformat(timestamp)
        start = start.replace(minute=5, second=0, microsecond=0)
    else:
        start = end - datetime.timedelta(days=7)
        # Ensure we start at the beginning of the day
        start = start.replace(hour=0, minute=5, second=0, microsecond=0)

    cur_dt = start
    while cur_dt < end:
        # After 24 hours, run daily trending for this day
        if cur_dt.hour == 0:
            day_dt = cur_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            print(f"Running daily trending for {day_dt.isoformat()}")
            daily_main(openlibrary_yml, timestamp=day_dt.isoformat(), dry_run=dry_run)

        print(f"Running hourly trending for {cur_dt.isoformat()}")
        hourly_main(openlibrary_yml, timestamp=cur_dt.isoformat(), dry_run=dry_run)

        cur_dt += datetime.timedelta(hours=1)

    print("Caught up to current time, stopping.")


if __name__ == '__main__':
    FnToCLI(main).run()
