import logging
import eventer
from celery.task import task

logger = logging.getLogger("openlibrary.tasks")

@task
def add(x, y):
    return x + y

@task
def trigger_offline_event(event, *a, **kw):
    logger.info("trigger_offline_event %s %s %s", event, a, kw)
    
    # Importing events to add an offline event to eventer. 
    # TODO: load the plugins from OL configuration
    from openlibrary.plugins.openlibrary import events
    
    eventer.trigger(event, *a, **kw)