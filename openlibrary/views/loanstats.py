"""Loan Stats"""
import re
import datetime
import web
from cStringIO import StringIO
import csv
from infogami.utils import delegate

from .. import app
from ..core import cache
from ..core.models import Bookshelves
from ..core.loanstats import LoanStats
from ..core.waitinglist import Stats as WLStats

class stats(app.view):
    path = "/stats"

    def GET(self):
        raise web.seeother("/stats/lending")

re_time_period1 = re.compile("(\d+)days")
re_time_period2 = re.compile("(\d\d\d\d)(\d\d)(\d\d)-(\d\d\d\d)(\d\d)(\d\d)")

class lending_stats(app.view):
    path = "/stats/lending(?:/(libraries|regions|countries|collections|subjects|format)/(.+))?"

    def is_enabled(self):
        return "loanstats" in web.ctx.features

    def GET(self, key, value):
        stats = LoanStats()
        if key == 'libraries':
            stats.library = value
        elif key == 'regions':
            stats.region = value
        elif key == 'countries':
            stats.country = value
        elif key == 'collections':
            stats.collection = value
        elif key == 'subjects':
            stats.subject = value
        elif key == 'subjects':
            stats.subject = value
        elif key == 'format':
            stats.resource_type = value

        i = web.input(t="30days", download=None)
        stats.time_period = self.parse_time(i.t)

        if i.download == "csv":
            return self.download_csv(stats, key, value)

        return app.render_template("stats/lending.html", stats)

    def download_csv(self, stats, key, value):
        pdf_counts = stats.get_raw_loans_per_day(resource_type="pdf")
        epub_counts = stats.get_raw_loans_per_day(resource_type="epub")
        bookreader_counts = stats.get_raw_loans_per_day(resource_type="bookreader")

        dates = sorted(set(pdf_counts.keys() + epub_counts.keys() + bookreader_counts.keys()))

        fileobj = StringIO()
        writer = csv.writer(fileobj)
        writer.writerow(["Date", "Total Loans", "PDF Loans", "ePub Loans", "Bookreader Loans"])
        for date in dates:
            pdf = pdf_counts.get(date, 0)
            epub = epub_counts.get(date, 0)
            bookreader = bookreader_counts.get(date, 0)
            total = pdf + epub + bookreader
            writer.writerow([date, total, pdf, epub, bookreader])
        filename = "{0}-{1}.csv".format(key, value)
        web.header("Content-disposition", "attachment; filename=" + filename)
        return delegate.RawText(fileobj.getvalue(), content_type="application/csv")

    def parse_time(self, t):
        m = re_time_period2.match(t)
        if m:
            y0, m0, d0, y1, m1, d1 = m.groups()
            begin = datetime.datetime(int(y0), int(m0), int(d0))
            end = datetime.datetime(int(y1), int(m1), int(d1))
        else:
            m = re_time_period1.match(t)
            if m:
                delta_days = int(m.group(1))
            else:
                delta_days = 30
            now = datetime.datetime.utcnow()
            begin = now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=delta_days)
            end = now
        return begin, end

class waitinglist_stats(app.view):
    path = "/stats/waitinglists"

    def is_enabled(self):
        return "wlstats" in web.ctx.features

    def GET(self):
        stats = WLStats()
        return app.render_template("stats/waitinglists.html", stats)

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
