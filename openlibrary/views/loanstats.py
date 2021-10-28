"""Loan Stats"""

import web
from infogami.utils import delegate
from ..core.lending import get_availabilities
from ..plugins.worksearch.code import DEFAULT_SEARCH_FIELDS
from ..plugins.worksearch.search import get_solr

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
    reading_log_summary, 'stats.readling_log_summary',
    timeout=dateutil.HOUR_SECS)


def reading_log_leaderboard(limit=None):
    # enable to work w/ cached
    if 'env' not in web.ctx:
        delegate.fakeload()

    most_read = Bookshelves.most_logged_books(
        Bookshelves.PRESET_BOOKSHELVES['Already Read'], limit=limit)
    most_wanted_all = Bookshelves.most_logged_books(
        Bookshelves.PRESET_BOOKSHELVES['Want to Read'], limit=limit)
    most_wanted_month = Bookshelves.most_logged_books(
        Bookshelves.PRESET_BOOKSHELVES['Want to Read'], limit=limit,
        since=dateutil.DATE_ONE_MONTH_AGO)
    return {
        'leaderboard': {
            'most_read': most_read,
            'most_wanted_all': most_wanted_all,
            'most_wanted_month': most_wanted_month,
            'most_rated_all': Ratings.most_rated_books()
        }
    }


def cached_reading_log_leaderboard(limit=None):
    return cache.memcache_memoize(
        reading_log_leaderboard, 'stats.readling_log_leaderboard',
        timeout=dateutil.HOUR_SECS )(limit)


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


class readinglog_stats(app.view):
    path = "/stats/readinglog"

    def GET(self):
        MAX_LEADERBOARD_SIZE = 50
        i = web.input(limit="10")
        limit = int(i.limit) if int(i.limit) < 51 else 50

        stats = get_cached_reading_log_stats(limit=limit)

        work_keys = {
            f"/works/OL{item['work_id']}W"
            for leaderboard in stats['leaderboard'].values()
            for item in leaderboard
        }
        solr_docs = {
            doc['key']: doc
            for doc in get_solr().get_many(work_keys, fields=DEFAULT_SEARCH_FIELDS)
        }

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
