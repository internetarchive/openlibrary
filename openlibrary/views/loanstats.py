"""Loan Stats"""

import re
import web
from infogami.utils import delegate

from ..utils import dateutil
from .. import app
from ..core import cache
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
        template = app.render_template("admin/index", counts)
        template.v2 = True
        return template


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

        # Fetch works from solr and inject into leaderboard
        for i in range(len(stats['leaderboard']['most_read'])):
            stats['leaderboard']['most_read'][i]['work'] = web.ctx.site.get(
                '/works/OL%sW' % stats['leaderboard']['most_read'][i]['work_id'])
        for i in range(len(stats['leaderboard']['most_wanted_all'])):
            stats['leaderboard']['most_wanted_all'][i]['work'] = web.ctx.site.get(
                '/works/OL%sW' % stats['leaderboard']['most_wanted_all'][i]['work_id'])
        for i in range(len(stats['leaderboard']['most_wanted_month'])):
            stats['leaderboard']['most_wanted_month'][i]['work'] = web.ctx.site.get(
                '/works/OL%sW' % stats['leaderboard']['most_wanted_month'][i]['work_id'])
        for i in range(len(stats['leaderboard']['most_rated_all'])):
            stats['leaderboard']['most_rated_all'][i]['work'] = web.ctx.site.get(
                '/works/OL%sW' % stats['leaderboard']['most_rated_all'][i]['work_id'])

        return app.render_template("stats/readinglog", stats=stats)
