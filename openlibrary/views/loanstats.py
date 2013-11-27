"""Loan Stats"""
import web
from .. import app
from ..core.loanstats import LoanStats

class stats(app.view):
    path = "/stats"

    def GET(self):
        raise web.seeother("/stats/lending")

class lending_stats(app.view):
    path = "/stats/lending"

    def GET(self):
        stats = LoanStats()
        return app.render_template("stats/lending.html", stats)
