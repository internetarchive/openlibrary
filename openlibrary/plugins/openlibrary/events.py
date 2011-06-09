"""Handling various events triggered by Open Library.
"""
from openlibrary.core import msgbroker, inlibrary
from infogami.infobase import client
import logging
import web

logger = logging.getLogger("openlibrary.events")

def on_library_edit(page):
    logger.info("%s is edited. Clearing library cache.", page['key'])
    inlibrary._get_libraries_memoized(_cache="delete")
    
def on_page_edit(page):
    if page.key.startswith("/libraries/"):
        msgbroker.send_message("page.edit.libraries", page)
    
class EditHook(client.hook):
    """Ugly Interface proivided by Infobase to get event notifications.
    """
    def on_new_version(self, page):
        """Fires page.edit event using msg broker."""
        # The argument passes by Infobase is not a thing object. 
        # Create a thing object to pass to event listeners.
        page = web.ctx.site.get(page['key'])
        msgbroker.send_message("page.edit", page)

def setup():
    """Installs handlers for various events.
    """
    msgbroker.subscribe("page.edit.libraries", on_library_edit)
    msgbroker.subscribe("page.edit", on_page_edit)