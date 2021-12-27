"""Loan Stats"""

import web
from infogami.utils import delegate
from ..core.lending import get_availabilities
from ..plugins.worksearch.code import get_solr_works

from ..utils import dateutil
from .. import app
from ..core import cache
from ..core.observations import Observations
from ..core.bookshelves import Bookshelves
from ..core.ratings import Ratings
from ..plugins.admin.code import get_counts


LENDING_TYPES = '(libraries|regions|countries|collections|subjects|format)'


def reading_log_summary():
    # enable to work w/ cached
    if 'env' not in web.ctx:
        delegate.fakeload()

    stats = Bookshelves.summary()
    stats.update(Ratings.summary())
    stats.update(Observations.summary())
    return stats


cached_reading_log_summary = cache.memcache_memoize(
    reading_log_summary, 'stats.readling_log_summary', timeout=dateutil.HOUR_SECS
)


def get_most_logged_books(shelf_id=None, since=dateutil.DATE_ONE_DAY_AGO, limit=20):
    """
    shelf_id: Bookshelves.PRESET_BOOKSHELVES['Want to Read'|'Already Read'|'Currently Reading']
    since: DATE_ONE_YEAR_AGO, DATE_ONE_MONTH_AGO, DATE_ONE_WEEK_AGO, DATE_ONE_DAY_AGO
    """
    # enable to work w/ cached
    if 'env' not in web.ctx:
        delegate.fakeload()

    return Bookshelves.most_logged_books(shelf_id=shelf_id, since=since, limit=limit)


def reading_log_leaderboard(limit=None):
    # enable to work w/ cached
    if 'env' not in web.ctx:
        delegate.fakeload()

    most_read = Bookshelves.most_logged_books(
        Bookshelves.PRESET_BOOKSHELVES['Already Read'], limit=limit
    )
    most_wanted_all = Bookshelves.most_logged_books(
        Bookshelves.PRESET_BOOKSHELVES['Want to Read'], limit=limit
    )
    most_wanted_month = Bookshelves.most_logged_books(
        Bookshelves.PRESET_BOOKSHELVES['Want to Read'],
        limit=limit,
        since=dateutil.DATE_ONE_MONTH_AGO,
    )
    return {
        'leaderboard': {
            'most_read': most_read,
            'most_wanted_all': most_wanted_all,
            'most_wanted_month': most_wanted_month,
            'most_rated_all': Ratings.most_rated_books(),
        }
    }


def cached_reading_log_leaderboard(limit=None):
    return cache.memcache_memoize(
        reading_log_leaderboard,
        'stats.readling_log_leaderboard',
        timeout=dateutil.HOUR_SECS,
    )(limit)


def get_cached_reading_log_stats(limit):
    stats = cached_reading_log_summary()
    stats.update(cached_reading_log_leaderboard(limit))
    return stats

class stats(app.view):
    path = "/stats"

    def GET(self):
        counts = get_counts()
        counts.reading_log = cached_reading_log_summary()
        return app.render_template("admin/index", counts)


class lending_stats(app.view):
    path = "/stats/lending(?:/%s/(.+))?" % LENDING_TYPES

    def GET(self, key, value):
        raise web.seeother("/")

def get_activity_stream(limit=None):
    # enable to work w/ cached
    if 'env' not in web.ctx:
        delegate.fakeload()
    return Bookshelves.get_recently_logged_books(limit=limit)

def get_cached_activity_stream(limit):
    return cache.memcache_memoize(
        get_activity_stream,
        'stats.activity_stream',
        timeout=dateutil.HOUR_SECS,
    )(limit)

class activity_stream(app.view):
    path = "/trending(/?.*)"

    def GET(self, page=''):
        if not page:
            raise web.seeother("/trending/now")
        page = page[1:]
        limit = 20
        if page == "now":
            logged_books = get_activity_stream(limit=limit)
        else:
            shelf_id = None  # optional; get from web.input()?
            logged_books = get_most_logged_books(since={
                'daily': dateutil.DATE_ONE_DAY_AGO,
                'weekly': dateutil.DATE_ONE_WEEK_AGO,
                'monthly': dateutil.DATE_ONE_MONTH_AGO,
                'yearly': dateutil.DATE_ONE_YEAR_AGO,
                'forever': None,
            }[page], limit=limit)

        work_index = get_solr_works(f"/works/OL{book['work_id']}W" for book in logged_books)
        availability_index = get_availabilities(work_index.values())
        for work_key in availability_index:
            work_index[work_key]['availability'] = availability_index[work_key]
        for i, logged_book in enumerate(logged_books):
            key = f"/works/OL{logged_book['work_id']}W"
            logged_books[i]['work'] = work_index[key]
        return app.render_template("trending", logged_books=logged_books, mode=page)


class readinglog_stats(app.view):
    path = "/stats/readinglog"

    def GET(self):
        MAX_LEADERBOARD_SIZE = 50
        i = web.input(limit="10", mode="all")
        limit = min(int(i.limit), 50)

        stats = get_cached_reading_log_stats(limit=limit)

        solr_docs = get_solr_works(
            f"/works/OL{item['work_id']}W"
            for leaderboard in stats['leaderboard'].values()
            for item in leaderboard
        )

        # Fetch works from solr and inject into leaderboard
        for leaderboard in stats['leaderboard'].values():
            for item in leaderboard:
                key = f"/works/OL{item['work_id']}W"
                if key in solr_docs:
                    item['work'] = solr_docs[key]
                else:
                    item['work'] = web.ctx.site.get(key)

        works = [
            item['work']
            for leaderboard in stats['leaderboard'].values()
            for item in leaderboard
        ]

        availabilities = get_availabilities(works)
        for leaderboard in stats['leaderboard'].values():
            for item in leaderboard:
                if availabilities.get(item['work']['key']):
                    item['availability'] = availabilities.get(item['work']['key'])

        return app.render_template("stats/readinglog", stats=stats)
