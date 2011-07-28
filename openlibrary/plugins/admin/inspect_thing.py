import datetime
import logging

import web
import couchdb

from infogami import config
from infogami.utils.view import render_template

tombstone_db = None
logger = None

class ComponentMissing(KeyError): pass
    


@web.memoize
def connect_to_tombstone():
    global tombstone_db
    try:
        tombstone_db_uri = config.get("celery",{})["tombstone_db"]
        tombstone_db = couchdb.Database(tombstone_db_uri)
    except Exception,e:
        logger.warning("Couldn't connect to tombstone database", exc_info = True)

def process_task_row(task):
    """Makes some changes to the task row from couch so that the
    template can display it properly"""
    print datetime.datetime.utcfromtimestamp(task.value['started_at'])
    task.value['started_at'] = datetime.datetime.utcfromtimestamp(task.value['started_at'])
    return task.value

def get_tasks_info(thing, tombstone_db):
    if not tombstone_db:
        return "Couldn't initialise connection to tombstone database. No task information available"
    events = tombstone_db.view("history/by_key",startkey=[thing], endkey=[thing,{}], include_docs=True)
    return (process_task_row(x) for x in events)


def get_thing_info(thing):
    global tombstone_db
    tasks = get_tasks_info(thing, tombstone_db)
    return render_template("admin/inspect/thing", thing, tasks)

def setup():
    global logger
    logger = logging.getLogger("openlibrary.inspect_thing")
    connect_to_tombstone()


