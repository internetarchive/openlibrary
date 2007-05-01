"""
links: allow interwiki links

Adds a markdown preprocessor to catch `[[foo]]` style links.
Creates a new set of database tables to keep track of them.
Creates a new `m=backlinks` to display the results.
"""

from infogami import utils
from infogami.utils import delegate

import view
from infogami import tdb
import db
import web

render = utils.view.render.links

class hook(tdb.hook):
    def on_new_version(self, page):
        if page.type.name == "page":
            db.new_links(page, view.get_links(page.body))

class backlinks (delegate.mode):
    def GET(self, site, path):
        links = db.get_links(site, path)
        return render.backlinks(links)
