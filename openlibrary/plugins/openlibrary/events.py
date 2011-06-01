"""Handling various events triggered by Open Library.
"""
from openlibrary.core import inlibrary
from openlibrary import tasks
from infogami.infobase import client
import logging
import web

import eventer

logger = logging.getLogger("openlibrary.events")

def on_library_edit(page):
    logger.info("%s is edited. Clearing library cache.", page['key'])
    inlibrary._get_libraries_memoized(_cache="delete")
    
def on_page_edit(page):
    if page.key.startswith("/libraries/"):
        eventer.trigger("page.edit.libraries", page)
    
class EditHook(client.hook):
    """Ugly Interface proivided by Infobase to get event notifications.
    """
    def on_new_version(self, page):
        """Fires page.edit event using msg broker."""
        # The argument passes by Infobase is not a thing object. 
        # Create a thing object to pass to event listeners.
        page = web.ctx.site.get(page['key'])
        eventer.trigger("page.edit", page)
        
        # Test event
        eventer.trigger("page.edit2", page.key)
        
@eventer.bind(None)
def trigger_offline_event(event, *a, **kw):
    """Triggers an offline event corresponds to this event.
    """
    logger.info("trigger_offline_event %s %s %s", event, a, kw)
    offline_event = "offline." + event
    
    # Getting the callbacks should be available from eventer API.
    if eventer._callbacks[offline_event]:
        logger.info("calling offline task")
        tasks.trigger_offline_event.delay(offline_event, *a, **kw)
        
@eventer.bind("offline.page.edit2")
def offline_page_edit(key):
    logger.info("Offline page edit event: %s", key)

def setup():
    """Installs handlers for various events.
    """
    eventer.bind("page.edit.libraries", on_library_edit)
    eventer.bind("page.edit", on_page_edit)
