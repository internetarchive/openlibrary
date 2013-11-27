"""Loan Stats"""
import web
from .. import app
from ..core.loanstats import LoanStats

class stats(app.view):
    path = "/stats"

    def GET(self):
        raise web.seeother("/stats/lending")

class lending_stats(app.view):
    path = "/stats/lending(?:/(libraries|regions)/(.+))?"

    def GET(self, key, value):
        stats = LoanStats()
        if key == 'libraries':
            stats.library = "/libraries/" + value
        elif key == 'regions':
            stats.region = value
        return app.render_template("stats/lending.html", stats)
