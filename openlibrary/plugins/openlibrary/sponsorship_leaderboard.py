"""Controller for sponsorship_leaderboard page.
"""

import web
import logging
import six
import random

from infogami.utils import delegate
from infogami.utils.view import render_template, public
from infogami.infobase.client import storify
from infogami import config
from openlibrary.core.bookshelves import Bookshelves

logger = logging.getLogger("openlibrary.home")

class sponsorship_leaderboard(delegate.page):
    path = "/sponsorship/leaderboard"

    def GET(self):
        random_books = [random.randint(1, 15) for i in range(20)]
        page = render_template("sponsorship_leaderboard" ,random_books , random_users= Bookshelves.get_n_users(20))
        page.v2 = True
        return page

def setup():
    pass