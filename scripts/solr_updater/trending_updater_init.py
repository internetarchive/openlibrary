import datetime

from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
from scripts.solr_updater.trending_updater_daily import main as daily_main
from scripts.solr_updater.trending_updater_hourly import main as hourly_main


def main(openlibrary_yml: str):
    now = datetime.datetime.now()
    start = now - datetime.timedelta(days=7)
    for day in range(8):
        day_dt = start + datetime.timedelta(days=day)
        for hour in range(24):
            ts = day_dt.replace(hour=hour, minute=5, second=0, microsecond=0)
            if ts > datetime.datetime.now():
                print("Caught up to current time, stopping.")
                return
            print(f"Running hourly trending for {ts.isoformat()}")
            hourly_main(openlibrary_yml, timestamp=ts.isoformat())
        # After 24 hours, run daily trending for this day
        print(f"Running daily trending for {day_dt.isoformat()}")
        daily_main(openlibrary_yml, timestamp=day_dt.isoformat())


if __name__ == '__main__':
    FnToCLI(main).run()
