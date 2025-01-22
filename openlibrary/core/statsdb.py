"""Interface to Open Library stats database.

The stats table in the openlibrary database is of the following schema:

    CREATE TABLE stats (
        id serial primary key,
        key text unique,
        type text,
        timestamp timestamp without time zone,
        json text
    );

see schema.py for more details.
"""

import datetime
import json
import logging

from .db import get_db

logger = logging.getLogger("openlibrary.statsdb")


def add_entry(key, data, timestamp=None):
    """Adds a new entry to the stats table.

    If an entry is already present in the table, a warn message is logged
    and no changes will be made to the database.
    """
    jsontext = json.dumps(data)
    timestamp = timestamp or datetime.datetime.utcnow()
    t = timestamp.isoformat()

    db = get_db()
    result = db.query("SELECT * FROM stats WHERE key=$key", vars=locals())
    if result:
        logger.warning(
            "Failed to add stats entry with key %r. An entry is already present."
        )
    else:
        db.insert("stats", type='loan', key=key, created=t, updated=t, json=jsontext)


def get_entry(key):
    result = get_db().query("SELECT * FROM stats WHERE key=$key", vars=locals())
    if result:
        return result[0]


def update_entry(key, data, timestamp=None):
    """Updates an already existing entry in the stats table.

    If there is no entry with the given key, a new one will be added
    after logging a warn message.
    """
    jsontext = json.dumps(data)
    timestamp = timestamp or datetime.datetime.utcnow()
    t = timestamp.isoformat()

    db = get_db()
    result = db.query("SELECT * FROM stats WHERE key=$key", vars=locals())
    if result:
        db.update("stats", json=jsontext, updated=t, where="key=$key", vars=locals())
    else:
        logger.warning(
            "stats entry with key %r doesn't exist to update. adding new entry...", key
        )
        db.insert("stats", type='loan', key=key, created=t, updated=t, json=jsontext)
