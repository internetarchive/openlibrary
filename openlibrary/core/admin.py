"""Admin functionality."""

import calendar
import datetime

import requests
import web

from infogami import config
from openlibrary.core import cache


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
        except (KeyError, StopIteration):
            self.total = ""

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
            t = datetime.datetime.strptime(d, "counts-%Y-%m-%d")
            return calendar.timegm(t.timetuple()) * 1000

        if times:
            return [
                [_convert_to_milli_timestamp(x['_key']), x.get(self.key, 0)]
                for x in self.docs[-ndays:]
            ]
        else:
            return zip(
                range(0, ndays * 5, 5), (x.get(self.key, 0) for x in self.docs[-ndays:])
            )  # The *5 and 5 are for the bar widths

    def get_summary(self, ndays=28):
        """Returns the summary of counts for past n days.

        Summary can be either sum or average depending on the type of stats.
        This is used to find counts for last 7 days and last 28 days.
        """
        return sum(x[1] for x in self.get_counts(ndays))


@cache.memoize(
    engine="memcache", key="admin._get_loan_counts_from_graphite", expires=5 * 60
)
def _get_loan_counts_from_graphite(ndays: int) -> list[list[int]] | None:
    try:
        r = requests.get(
            'http://graphite.us.archive.org/render',
            params={
                'target': 'hitcount(stats.ol.loans.bookreader, "1d")',
                'from': '-%ddays' % ndays,
                'tz': 'UTC',
                'format': 'json',
            },
        )
        return r.json()[0]['datapoints']
    except (requests.exceptions.RequestException, ValueError, AttributeError):
        return None


class LoanStats(Stats):
    """
    Temporary (2020-03-19) override of Stats for loans, due to bug
    which caused 1mo of loans stats to be missing from regular
    stats db. This implementation uses graphite, but only on prod,
    so that we don't forget.
    """

    def get_counts(self, ndays=28, times=False):
        # Let dev.openlibrary.org show the true state of things
        if 'dev' in config.features:
            return Stats.get_counts(self, ndays, times)

        if graphite_data := _get_loan_counts_from_graphite(ndays):
            # convert timestamp seconds to ms (as required by API)
            return [[timestamp * 1000, count] for [count, timestamp] in graphite_data]
        else:
            return Stats.get_counts(self, ndays, times)


@cache.memoize(
    engine="memcache", key="admin._get_visitor_counts_from_graphite", expires=5 * 60
)
def _get_visitor_counts_from_graphite(self, ndays: int = 28) -> list[list[int]]:
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
        )
        response.raise_for_status()
        visitors = response.json()[0]['datapoints']
    except requests.exceptions.RequestException:
        visitors = []
    return visitors


class VisitorStats(Stats):
    def get_counts(self, ndays: int = 28, times: bool = False) -> list[tuple[int, int]]:
        visitors = _get_visitor_counts_from_graphite(ndays)
        # Flip the order, convert timestamp to msec, and convert count==None to zero
        return [
            (int(timestamp * 1000), int(count or 0)) for count, timestamp in visitors
        ]


@cache.memoize(engine="memcache", key="admin._get_count_docs", expires=5 * 60)
def _get_count_docs(ndays):
    """Returns the count docs from admin stats database.

    This function is memoized to avoid accessing the db for every request.
    """
    today = datetime.datetime.utcnow().date()
    dates = [today - datetime.timedelta(days=i) for i in range(ndays)]

    # we want the dates in reverse order
    dates = dates[::-1]

    docs = [web.ctx.site.store.get(d.strftime("counts-%Y-%m-%d")) for d in dates]
    return [d for d in docs if d]


def get_stats(ndays=30, use_mock_data=False):
    """Returns the stats for the past `ndays`"""
    if use_mock_data:
        return mock_get_stats()
    docs = _get_count_docs(ndays)
    return {
        'human_edits': Stats(docs, "human_edits", "human_edits"),
        'bot_edits': Stats(docs, "bot_edits", "bot_edits"),
        'lists': Stats(docs, "lists", "total_lists"),
        'visitors': VisitorStats(docs, "visitors", "visitors"),
        'loans': LoanStats(docs, "loans", "loans"),
        'members': Stats(docs, "members", "total_members"),
        'works': Stats(docs, "works", "total_works"),
        'editions': Stats(docs, "editions", "total_editions"),
        'ebooks': Stats(docs, "ebooks", "total_ebooks"),
        'covers': Stats(docs, "covers", "total_covers"),
        'authors': Stats(docs, "authors", "total_authors"),
        'subjects': Stats(docs, "subjects", "total_subjects"),
    }


def mock_get_stats():
    keyNames = [
        "human_edits",
        "bot_edits",
        "lists",
        "visitors",
        "loans",
        "members",
        "works",
        "editions",
        "ebooks",
        "covers",
        "authors",
        "subjects",
    ]
    mockKeyValues = [[(1 + x) * y for x in range(len(keyNames))] for y in range(28)][
        ::-1
    ]

    docs = [dict(zip(keyNames, mockKeyValues[x])) for x in range(len(mockKeyValues))]
    today = datetime.date.today()
    for x in range(28):
        docs[x]["_key"] = (today - datetime.timedelta(days=x + 1)).strftime(
            'counts-%Y-%m-%d'
        )
    return {
        'human_edits': Stats(docs, "human_edits", "human_edits"),
        'bot_edits': Stats(docs, "bot_edits", "bot_edits"),
        'lists': Stats(docs, "lists", "total_lists"),
        'visitors': Stats(docs, "visitors", "visitors"),
        'loans': Stats(docs, "loans", "loans"),
        'members': Stats(docs, "members", "total_members"),
        'works': Stats(docs, "works", "total_works"),
        'editions': Stats(docs, "editions", "total_editions"),
        'ebooks': Stats(docs, "ebooks", "total_ebooks"),
        'covers': Stats(docs, "covers", "total_covers"),
        'authors': Stats(docs, "authors", "total_authors"),
        'subjects': Stats(docs, "subjects", "total_subjects"),
    }
