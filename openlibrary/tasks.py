import logging
import eventer
from openlibrary.core.task import oltask

from openlibrary.core import formats
from openlibrary.core.lists.updater import Updater as ListUpdater

logger = logging.getLogger("openlibrary.tasks")

try:
    import celeryconfig
except ImportError:
    logger.error("failed to import celeryconfig")
    celeryconfig = None


@oltask
def add(x, y):
    return x + y

@oltask
def trigger_offline_event(event, *a, **kw):
    logger.info("trigger_offline_event %s %s %s", event, a, kw)
    
    # Importing events to add an offline event to eventer. 
    # TODO: load the plugins from OL configuration
    from openlibrary.plugins.openlibrary import events
    
    eventer.trigger(event, *a, **kw)
    
@oltask
def on_edit(changeset):
    """This gets triggered whenever an edit happens on Open Library.
    """
    update_lists.delay(changeset)
    update_solr.delay(changeset)
    
@oltask
def update_lists(changeset):
    """Updates the lists database on edit.
    """
    logger.info("update_lists: %s", changeset['id'])
    configfile = celeryconfig.OL_CONFIG
    ol_config = formats.load_yaml(open(configfile).read())
    
    updater = ListUpdater(ol_config.get("lists"))
    updater.process_changeset(changeset, update_seeds=True)

@oltask
def update_solr(changeset):
    """Updates solr on edit.
    """
    pass
