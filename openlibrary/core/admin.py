"""Admin functionality."""

import calendar
import random
from datetime import UTC, date, datetime, timedelta

import requests
import web

from openlibrary.core import cache
from openlibrary.core.async_db import fetch_val
from openlibrary.core.env import get_ol_env
from openlibrary.core.helpers import commify, format_date


class Stats:
    def __init__(self, docs, key, total_key):
        self.key = key
        self.docs = docs
        try:
            self.latest = docs[-1].get(key, 0)
        except IndexError:
            self.latest = 0

        try:
            self.previous = docs[-2].get(key, 0)
        except IndexError:
            self.previous = 0

        try:
            # Last available total count
            self.total = next(x for x in reversed(docs) if total_key in x)[total_key]
        except KeyError, StopIteration:
            self.total = ""

    def has_counts(self, ndays=28) -> bool:
        """True when every doc of the last `ndays` carries this key. A key only some of them
        have is one the stats script started writing recently, and a series read from it would
        cover part of the window while claiming all of it."""
        docs = self.docs[-ndays:]
        return bool(docs) and all(self.key in doc for doc in docs)

    def get_counts(self, ndays=28, times=False):
        """Returns the stats for last n days as an array useful for
        plotting. i.e. an array of [x, y] tuples where y is the value
        and `x` the x coordinate.

        If times is True, the x coordinate in the tuple will be
        timestamps for the day.
        """

        def _convert_to_milli_timestamp(d):
            """Uses the `_id` of the document `d` to create a UNIX
            timestamp and converts it to milliseconds"""
            t = datetime.strptime(d, "counts-%Y-%m-%d")
            return calendar.timegm(t.timetuple()) * 1000

        if times:
            return [[_convert_to_milli_timestamp(x["_key"]), x.get(self.key, 0)] for x in self.docs[-ndays:]]
        else:
            return zip(range(0, ndays * 5, 5), (x.get(self.key, 0) for x in self.docs[-ndays:]))  # The *5 and 5 are for the bar widths

    def get_bar_chart(self, ndays: int, width: int, height: int) -> dict:
        """Data for a daily bar chart of the last `ndays`, drawn by StatsBarChart.html.jinja.

        Bars are oldest first and scaled so the busiest day fills `height`.
        """
        counts = sorted(self.get_counts(ndays, True))
        peak = max((count for _, count in counts), default=0) or 1
        step = width / max(len(counts), 1)
        bars = []
        for i, (timestamp, count) in enumerate(counts):
            bar_height = count / peak * height
            day = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
            bars.append(
                {
                    "x": round(i * step, 2),
                    "y": round(height - bar_height, 2),
                    "height": round(bar_height, 2),
                    "title": f"{format_date(day)}: {commify(count)}",
                }
            )
        return {
            "width": width,
            "height": height,
            "bar_step": round(step, 2),
            "bar_width": round(step - min(1, step / 4), 2),
            "bars": bars,
        }

    def get_summary(self, ndays=28):
        """Returns the summary of counts for past n days.

        Summary can be either sum or average depending on the type of stats.
        This is used to find counts for last 7 days and last 28 days.
        """
        return sum(x[1] for x in self.get_counts(ndays))


@cache.memoize(engine="memcache", key="admin._get_loan_counts_from_graphite", expires=5 * 60)
def _get_loan_counts_from_graphite(ndays: int) -> list[list[int]]:
    try:
        r = requests.get(
            "http://graphite.us.archive.org/render",
            params={
                "target": 'hitcount(stats.ol.loans.bookreader, "1d")',
                "from": "-%ddays" % ndays,
                "tz": "UTC",
                "format": "json",
            },
            timeout=5,
        )
        r.raise_for_status()
        return r.json()[0]["datapoints"]
    except requests.exceptions.RequestException, ValueError, AttributeError:
        # Return [] rather than None: cache.memoize treats None as a cache miss,
        # so caching a failure would otherwise re-hit the 5s timeout on every
        # request while Graphite is down. Callers test truthiness.
        return []


class LoanStats(Stats):
    """
    Loan counts come from graphite; the daily counts docs don't track
    loans, so the fallback (e.g. local dev) reports zero.
    """

    def has_counts(self, ndays=28) -> bool:
        if get_ol_env().LOCAL_DEV or not _get_loan_counts_from_graphite(ndays):
            return Stats.has_counts(self, ndays)
        return True

    def get_counts(self, ndays=28, times=False):
        # Let dev.openlibrary.org show the true state of things
        if get_ol_env().LOCAL_DEV:
            return Stats.get_counts(self, ndays, times)

        if graphite_data := _get_loan_counts_from_graphite(ndays):
            # Convert timestamp seconds to ms (as required by API); Graphite reports None for days with no data yet (e.g. today)
            return [[timestamp * 1000, count or 0] for [count, timestamp] in graphite_data]
        else:
            return Stats.get_counts(self, ndays, times)


@cache.memoize(engine="memcache", key="admin._get_visitor_counts_from_graphite", expires=5 * 60)
def _get_visitor_counts_from_graphite(ndays: int = 28) -> list[list[int]]:
    """
    Read the unique visitors (IP addresses) per day for the last ndays from graphite.
    :param ndays: number of days to read
    :return: list containing [count, timestamp] for ndays
    """
    try:
        response = requests.get(
            "http://graphite.us.archive.org/render/",
            params={
                "target": "summarize(stats.uniqueips.openlibrary, '1d')",
                "from": f"-{ndays}days",
                "tz": "UTC",
                "format": "json",
            },
            timeout=5,
        )
        response.raise_for_status()
        visitors = response.json()[0]["datapoints"]
    except requests.exceptions.RequestException:
        visitors = []
    return visitors


class VisitorStats(Stats):
    def has_counts(self, ndays: int = 28) -> bool:
        return bool(_get_visitor_counts_from_graphite(ndays))

    def get_counts(self, ndays: int = 28, times: bool = False) -> list[tuple[int, int]]:
        visitors = _get_visitor_counts_from_graphite(ndays)
        # Flip the order, convert timestamp to msec, and convert count==None to zero
        return [(int(timestamp * 1000), int(count or 0)) for count, timestamp in visitors]


@cache.memoize(engine="memcache", key="admin._get_count_docs", expires=5 * 60)
def _get_count_docs(ndays):
    """Returns the count docs from admin stats database.

    This function is memoized to avoid accessing the db for every request.
    """
    today = date.today()
    dates = [today - timedelta(days=i) for i in range(ndays)]

    # we want the dates in reverse order
    dates.reverse()

    docs = [web.ctx.site.store.get(d.strftime("counts-%Y-%m-%d")) for d in dates]
    return [d for d in docs if d]


def get_stats(ndays=30, use_mock_data=False):
    """Returns the stats for the past `ndays`"""
    if use_mock_data:
        return mock_get_stats(ndays)
    docs = _get_count_docs(ndays)
    return {
        "human_edits": Stats(docs, "human_edits", "human_edits"),
        "bot_edits": Stats(docs, "bot_edits", "bot_edits"),
        "catalog_edits": Stats(docs, "catalog_edits", "catalog_edits"),
        "lists": Stats(docs, "lists", "total_lists"),
        "list_edits": Stats(docs, "list_edits", "list_edits"),
        "visitors": VisitorStats(docs, "visitors", "visitors"),
        "loans": LoanStats(docs, "loans", "loans"),
        "members": Stats(docs, "members", "total_members"),
        "works": Stats(docs, "works", "total_works"),
        "editions": Stats(docs, "editions", "total_editions"),
        "ebooks": Stats(docs, "ebooks", "total_ebooks"),
        "covers": Stats(docs, "covers", "total_covers"),
        "authors": Stats(docs, "authors", "total_authors"),
        "subjects": Stats(docs, "subjects", "total_subjects"),
    }


@cache.memoize(engine="memcache", key="logins_since", expires=12 * 60 * 60)
async def get_unique_logins_since(since_days=30):
    since_date = datetime.now() - timedelta(days=since_days)
    date_str = since_date.strftime("%Y-%m-%d")

    query = """
        SELECT COUNT(*) FROM store_index
            WHERE type = 'account'
            AND name = 'last_login'
            AND value > %(date)s
    """

    count = await fetch_val(query, {"date": date_str})
    return count or 0


def mock_get_stats(ndays=30):
    """Daily counts shaped like production's for local dev: a weekend dip, some noise and a
    gentle climb, at roughly production's scale. Seeded per key so a reload doesn't redraw."""
    daily_scale = {
        "human_edits": 12_000,
        "bot_edits": 20_000,
        "catalog_edits": 3_000,
        "lists": 150,
        "list_edits": 1_200,
        "visitors": 5_800_000,
        "loans": 10_000,
        "members": 7_000,
        "works": 3_000,
        "editions": 5_000,
        "ebooks": 100,
        "covers": 2_000,
        "authors": 1_500,
        "subjects": 500,
    }
    today = date.today()
    days = [today - timedelta(days=n) for n in range(ndays, 0, -1)]
    docs = [{"_key": day.strftime("counts-%Y-%m-%d")} for day in days]
    for key, scale in daily_scale.items():
        rng = random.Random(key)
        for i, (day, doc) in enumerate(zip(days, docs, strict=True)):
            weekend = 0.85 if day.weekday() >= 5 else 1.0
            climb = 0.85 + 0.3 * i / max(ndays - 1, 1)
            doc[key] = round(scale * weekend * climb * rng.uniform(0.92, 1.08))
    return {key: Stats(docs, key, f"total_{key}") for key in daily_scale}
