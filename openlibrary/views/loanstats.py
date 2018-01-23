"""Loan Stats"""

import re
import datetime
import web
from infogami.utils import delegate

from .. import app
from ..core import cache
from ..core.bookshelves import Bookshelves

class stats(app.view):
    path = "/stats"

    def GET(self):
        raise web.seeother("/")

class lending_stats(app.view):
    path = "/stats/lending(?:/(libraries|regions|countries|collections|subjects|format)/(.+))?"

    def GET(self, key, value):
        raise web.seeother("/")

class readinglog_stats(app.view):
    path = "/stats/readinglog"

    def GET(self):
        ONE_MONTH_DATE = datetime.date.today() - datetime.timedelta(days=28)
        MAX_LEADERBOARD_SIZE = 50
        i = web.input(limit="10")
        limit = int(i.limit) if int(i.limit) < 51 else 50

        def readinglog_stats(limit=limit):
            if 'env' not in web.ctx:
                delegate.fakeload()
            most_read = Bookshelves.most_logged_books(
                Bookshelves.PRESET_BOOKSHELVES['Already Read'], limit=limit)
            most_wanted = Bookshelves.most_logged_books(
                Bookshelves.PRESET_BOOKSHELVES['Want to Read'], limit=limit)

            return {
                'total_books_logged': {
                    'total': Bookshelves.total_books_logged(),
                    'month': Bookshelves.total_books_logged(since=ONE_MONTH_DATE)
                },
                'total_users_logged': {
                    'total': Bookshelves.total_unique_users(),
                    'month': Bookshelves.total_unique_users(since=ONE_MONTH_DATE)
                },
                'leaderboard': {
                    'most_read': most_read,
                    'most_wanted': most_wanted
                }
            }
        stats =  cache.memcache_memoize(
            readinglog_stats, 'stats.readlinglog_stats', timeout=cache.HOUR)(limit)

        # Fetch works from solr and inject into leaderboard
        for i in range(len(stats['leaderboard']['most_read'])):
            stats['leaderboard']['most_read'][i]['work'] = web.ctx.site.get(
                '/works/OL%sW' % stats['leaderboard']['most_read'][i]['work_id'])
        for i in range(len(stats['leaderboard']['most_wanted'])):
            stats['leaderboard']['most_wanted'][i]['work'] = web.ctx.site.get(
                '/works/OL%sW' % stats['leaderboard']['most_wanted'][i]['work_id'])

        return app.render_template("stats/readinglog", stats=stats)
