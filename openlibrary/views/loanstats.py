"""Loan Stats"""

from collections.abc import Iterable

import web

from infogami.utils import delegate
from infogami.utils.view import public

from .. import app
from ..core import cache
from ..core.booknotes import Booknotes
from ..core.bookshelves import Bookshelves
from ..core.follows import PubSub
from ..core.lending import get_availabilities
from ..core.observations import Observations
from ..core.ratings import Ratings
from ..core.yearly_reading_goals import YearlyReadingGoals
from ..plugins.admin.code import get_counts
from ..plugins.worksearch.code import get_solr_works
from ..utils import dateutil

LENDING_TYPES = "(libraries|regions|countries|collections|subjects|format)"


SINCE_DAYS = {
    "now": 0,
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "yearly": 365,
    "forever": None,
}


@cache.memoize("memcache", "stats.reading_log_summary", expires=dateutil.HOUR_SECS)
def reading_log_summary():
    # enable to work w/ cached
    if "env" not in web.ctx:
        delegate.fakeload()

    stats = Bookshelves.summary()
    stats.update(YearlyReadingGoals.summary())
    stats.update(Ratings.summary())
    stats.update(Observations.summary())
    stats.update(Booknotes.summary())
    stats.update(PubSub.summary())
    return stats


@public
def get_trending_books(
    since_days=1,
    since_hours=0,
    limit=18,
    page=1,
    sort_by_count=True,
    minimum=0,
    fields: Iterable[str] | None = None,
):
    logged_books = (
        Bookshelves.get_recently_logged_books(limit=limit, page=page)
        if (since_days == 0 and since_hours == 0)
        else Bookshelves.most_logged_books(
            since=dateutil.todays_date_minus(days=since_days, hours=since_hours),
            limit=limit,
            page=page,
            sort_by_count=sort_by_count,
            minimum=minimum,
        )
    )
    Bookshelves.add_solr_works(logged_books, fields=fields)

    return [book["work"] for book in logged_books if book.get("work")]


@cache.memoize("memcache", "stats.trending", expires=dateutil.HOUR_SECS)
def cached_get_most_logged_books(
    shelf_id: int | None = None,
    since_days=1,
    limit=20,
    page=1,
):
    return Bookshelves.most_logged_books(
        shelf_id=shelf_id,
        since=dateutil.date_n_days_ago(since_days),
        limit=limit,
        page=page,
    )


def reading_log_leaderboard(limit: int):
    # enable to work w/ cached
    if "env" not in web.ctx:
        delegate.fakeload()

    most_read = Bookshelves.most_logged_books(Bookshelves.PRESET_BOOKSHELVES["Already Read"], limit=limit)
    most_wanted_all = Bookshelves.most_logged_books(Bookshelves.PRESET_BOOKSHELVES["Want to Read"], limit=limit)
    most_wanted_month = Bookshelves.most_logged_books(
        Bookshelves.PRESET_BOOKSHELVES["Want to Read"],
        limit=limit,
        since=dateutil.DATE_ONE_MONTH_AGO,
    )
    return {
        "leaderboard": {
            "most_read": most_read,
            "most_wanted_all": most_wanted_all,
            "most_wanted_month": most_wanted_month,
            "most_rated_all": Ratings.most_rated_books(),
        }
    }


def get_cached_reading_log_stats(limit: int):
    @cache.memoize("memcache", "stats.readling_log_leaderboard", expires=dateutil.HOUR_SECS)
    def cached_reading_log_leaderboard(limit: int):
        return reading_log_leaderboard(limit)

    stats = reading_log_summary()
    stats.update(cached_reading_log_leaderboard(limit))
    return stats


class stats(app.view):
    path = "/stats"

    def GET(self):
        counts = get_counts()
        counts.reading_log = reading_log_summary()
        return app.render_template("admin/index", counts)


class lending_stats(app.view):
    path = "/stats/lending(?:/%s/(.+))?" % LENDING_TYPES

    def GET(self, key, value):
        raise web.seeother("/")


class activity_stream(app.view):
    path = "/trending(/?.*)"

    def GET(self, mode=""):
        i = web.input(page=1)
        page = i.page
        if not mode:
            raise web.seeother("/trending/now")
        mode = mode[1:]  # remove slash
        limit = 20
        if mode == "now":
            logged_books = Bookshelves.get_recently_logged_books(limit=limit, page=page)

        else:
            logged_books = cached_get_most_logged_books(since_days=SINCE_DAYS[mode], limit=limit, page=page)
        Bookshelves.add_solr_works(logged_books)
        return app.render_template("trending", logged_books=logged_books, mode=mode)


class readinglog_stats(app.view):
    path = "/stats/readinglog"

    def GET(self):
        MAX_LEADERBOARD_SIZE = 50
        i = web.input(limit="10", mode="all")
        limit = min(int(i.limit), MAX_LEADERBOARD_SIZE)

        stats = get_cached_reading_log_stats(limit)

        solr_docs = get_solr_works({f"/works/OL{item['work_id']}W" for leaderboard in stats["leaderboard"].values() for item in leaderboard})

        # Fetch works from solr and inject into leaderboard
        for leaderboard in stats["leaderboard"].values():
            for item in leaderboard:
                key = f"/works/OL{item['work_id']}W"
                if key in solr_docs:
                    item["work"] = solr_docs[key]
                else:
                    item["work"] = web.ctx.site.get(key)

        works = [item["work"] for leaderboard in stats["leaderboard"].values() for item in leaderboard]

        availabilities = get_availabilities(works)
        for leaderboard in stats["leaderboard"].values():
            for item in leaderboard:
                if availabilities.get(item["work"]["key"]):
                    item["availability"] = availabilities.get(item["work"]["key"])

        return app.render_template("stats/readinglog", stats=stats)
