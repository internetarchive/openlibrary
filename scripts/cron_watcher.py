#!/usr/bin/env python3

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

import bs4
import httpx

DATA_DUMPS_URL = "https://archive.org/details/ol_exports?sort=-publicdate"
# Last day of last month is the first day of this month minus one day.
last_day_of_last_month = date.today().replace(day=1) - timedelta(days=1)
yyyy_mm = f"{last_day_of_last_month:%Y-%m}"


async def find_last_months_dumps_on_ia(yyyy_mm: str = yyyy_mm) -> bool:
    """
    Return True if both ol_dump_yyyy and ol_cdump_yyyy files have been saved on the
    Internet Archive.
    """
    prefixes = (f"ol_dump_{yyyy_mm}", f"ol_cdump_{yyyy_mm}")
    # print(prefixes)
    async with httpx.AsyncClient() as client:
        response = await client.get(DATA_DUMPS_URL)
    response.raise_for_status()
    soup = bs4.BeautifulSoup(response.content, features="html.parser")
    found = 0
    # <div class="item-ia" data-id="ol_dump_2019-10-31" data-mediatype="data">
    for item_ia in soup.find_all("div", class_="item-ia"):
        if item_ia["data-id"].startswith(prefixes):
            # print(item_ia["data-id"])
            found += 1
            if found >= 2:
                break
    return found >= 2


if __name__ == "__main__":
    import asyncio
    import sys

    both_files_found = asyncio.run(find_last_months_dumps_on_ia())
    print(f"{both_files_found = }")
    if not both_files_found:
        sys.exit(1)
