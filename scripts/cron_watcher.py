#!/usr/bin/env python

"""
Daily Cron-audit task (Python) sentry (who watches the watchers)
If not dump and cdump uploaded for last YYYY-MM on archive.org
If not sitemaps updated for this YYYY-MM on www
If not partner dumps uploaded for this YYYY-MM on archive.org
If no imports in last 48 hours (i.e. 2 days)
If DD>17 for YYYY-MM and bwb `batchname` doesn’t exist in import psql table
Send daily email with failures only or slack failures
"""

from datetime import date, timedelta

from internetarchive import search_items

# Last day of last month is the first day of this month minus one day.
last_day_of_last_month = date.today().replace(day=1) - timedelta(days=1)
yyyy_mm = f"{last_day_of_last_month:%Y-%m}"


def find_last_months_dumps_on_ia(yyyy_mm: str = yyyy_mm) -> bool:
    """
    Return True if both ol_dump_yyyy_mm and ol_cdump_yyyy_mm files
    have been saved on Internet Archive collection:ol_exports.

    >>> next_month = date.today().replace(day=1) + timedelta(days=31)
    >>> find_last_months_dumps_on_ia(f"{next_month:%Y-%m}")
    False
    """
    prefixes = {f"ol_dump_{yyyy_mm}": 0, f"ol_cdump_{yyyy_mm}": 0}
    # print(prefixes)
    for item in search_items("collection:ol_exports"):
        for prefix in prefixes:
            if item["identifier"].startswith(prefix):
                prefixes[prefix] += 1
                # Is there at least one item id starting with each prefix?
                if files_with_both_prefixes_found := all(prefixes.values()):
                    return files_with_both_prefixes_found
    return all(prefixes.values())


if __name__ == "__main__":
    import sys

    files_with_both_prefixes_found = find_last_months_dumps_on_ia()
    print(f"{files_with_both_prefixes_found = }")
    if not files_with_both_prefixes_found:
        sys.exit(1)
