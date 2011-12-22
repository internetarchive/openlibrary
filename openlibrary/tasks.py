import logging
import eventer
import urllib2
from openlibrary.core.task import oltask, set_task_data
from openlibrary.core.fetchmail import fetchmail
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
def update_support_from_email():
    configfile = celeryconfig.OL_CONFIG
    ol_config = formats.load_yaml(open(configfile).read())
    fetchmail(ol_config)

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
    for t in other_on_edit_tasks:
        t.delay(changeset)

# Hook to add other on-edit tasks.
# Used by dev_instance.py
other_on_edit_tasks = []
    
@oltask
def update_lists(changeset):
    """Updates the lists database on edit.
    """
    keys = [x['key'] for x in changeset['docs']]
    set_task_data(keys = keys, changeset = changeset['id'])
    logger.info("BEGIN update_lists: %s", changeset['id'])
    configfile = celeryconfig.OL_CONFIG
    ol_config = formats.load_yaml(open(configfile).read())
    
    updater = ListUpdater(ol_config.get("lists"))
    updater.process_changeset(changeset, update_seeds=False)
    logger.info("END update_lists")

@oltask
def upload_via_s3(item_id, filename, data, s3_key, s3_secret):
    logger.info("s3 upload: %s %s" % (item_id, filename) )

    path = "http://s3.us.archive.org/%s/%s" % (item_id, filename)
    auth = "LOW %s:%s" % (s3_key, s3_secret)

    req = urllib2.Request(path)
    req.add_header('x-archive-auto-make-bucket', '1')
    req.add_header('x-archive-meta-collection',  'ol_data')
    req.add_header('x-archive-meta-mediatype',   'data')
    req.add_header('x-archive-keep-old-version', '1')
    req.add_header('x-archive-queue-derive',     '0')
    req.add_header('authorization', auth)

    req.add_data(data)
    req.get_method = lambda: 'PUT'

    f = urllib2.urlopen(req)
    logger.info('s3 upload of %s %s returned status: %d' % (item_id, filename, f.getcode()))


def setup():
    # make sure openlibrary logger has at least INFO level
    ol_logger = logging.getLogger("openlibrary")
    if ol_logger.level < logging.INFO:
        ol_logger.level = logging.INFO
    
setup()
