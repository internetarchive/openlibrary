"""Handling various events triggered by Open Library.
"""
from infogami.infobase import client
import logging
import web

import eventer

logger = logging.getLogger("openlibrary.events")

def on_page_edit(page):
    pass

class EditHook(client.hook):
    """Ugly Interface provided by Infobase to get event notifications.
    """
    def on_new_version(self, page):
        """Fires page.edit event using msg broker."""
        # The argument passes by Infobase is not a thing object.
        # Create a thing object to pass to event listeners.
        page = web.ctx.site.get(page['key'])
        eventer.trigger("page.edit", page)

def setup():
    """Installs handlers for various events.
    """
    eventer.bind("page.edit", on_page_edit)
