"""Loan Stats"""
import re
import datetime
import web

from .. import app
from ..core.loanstats import LoanStats

class stats(app.view):
    path = "/stats"

    def GET(self):
        raise web.seeother("/stats/lending")

re_time_period1 = re.compile("(\d+)days")
#re_time_period2 = re.compile("(\d\d\d)(\d\d)(\d\d)-(\d\d\d\d)(\d\d)(\d\d)")

class lending_stats(app.view):
    path = "/stats/lending(?:/(libraries|regions|collections|subjects|format)/(.+))?"

    def GET(self, key, value):
        stats = LoanStats()
        if key == 'libraries':
            stats.library = value
        elif key == 'regions':
            stats.region = value
        elif key == 'collections':
            stats.collection = value
        elif key == 'subjects': 
            stats.subject = value
        elif key == 'subjects': 
            stats.subject = value
        elif key == 'format': 
            stats.resource_type = value

        i = web.input(t="30days")
        stats.time_period = self.parse_time(i.t)

        return app.render_template("stats/lending.html", stats)

    def parse_time(self, t):
        m = re_time_period1.match(t)
        if m:
            delta_days = int(m.group(1))
        else:
            delta_days = 30
        now = datetime.datetime.utcnow()
        begin = now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=delta_days)
        end = now
        return begin, end
