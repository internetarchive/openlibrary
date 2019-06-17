"""Controller for home page.
"""

import web
import logging
import six

from infogami.utils import delegate
from infogami.utils.view import render_template, public
from infogami.infobase.client import storify
from infogami import config

logger = logging.getLogger("openlibrary.home")

class sponsorship(delegate.page):
    path = "/account/sponsorships"

    def GET(self):
        i = web.input(book='OL..M')
        page = render_template("account/sponsorships", book=i.book)
        page.v2 = True
        return page

def setup():
    pass
