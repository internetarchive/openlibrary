import datetime

from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
from scripts.solr_updater.trending_updater_daily import main as daily_main
from scripts.solr_updater.trending_updater_hourly import main as hourly_main


def main(
    openlibrary_yml: str,
    timestamp: str | None = None,
    dry_run: bool = False,
):
    end = datetime.datetime.now()
    if timestamp:
        start = datetime.datetime.fromisoformat(timestamp)
    else:
        start = end - datetime.timedelta(days=7)
    days = (end - start).days

    for day in range(days + 1):
        day_dt = start + datetime.timedelta(days=day)
        for hour in range(24):
            ts = day_dt.replace(hour=hour, minute=5, second=0, microsecond=0)
            if ts > datetime.datetime.now():
                print("Caught up to current time, stopping.")
                return
            print(f"Running hourly trending for {ts.isoformat()}")
            hourly_main(openlibrary_yml, timestamp=ts.isoformat(), dry_run=dry_run)
        # After 24 hours, run daily trending for this day
        print(f"Running daily trending for {day_dt.isoformat()}")
        daily_main(openlibrary_yml, timestamp=day_dt.isoformat(), dry_run=dry_run)


if __name__ == '__main__':
    FnToCLI(main).run()
