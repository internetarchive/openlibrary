"""Library to talk directly to OL database to avoid expensive API calls.
"""
import web
import simplejson

import config

from openlibrary.utils import olmemcache

__all__ = [
    "query", "get"
]

def is_supported():
    return bool(config.get("ol_db_parameters"))

_db = None
def get_db():
    global _db
    if _db is None and config.get("ol_db_parameters"):
        _db = web.database(**config.ol_db_parameters)
    return _db
    
_memcache = None
def get_memcache():
    global _memcache
    if _memcache is None and config.get("ol_memcache_servers"):
        _memcache = olmemcache.Client(config.ol_memcache_servers)
    return _memcache

@web.memoize
def get_property_id(name):
    db = get_db()
    try:
        type_id = db.query("SELECT * FROM thing WHERE key='/type/edition'")[0].id
        rows = db.query("SELECT * FROM property WHERE name=$name AND type=$type_id", vars=locals())
        return rows[0].id
    except IndexError:
        return None
    
def query(key, value):
    key_id = get_property_id(key)
    
    db = get_db()
    rows = db.query("SELECT thing.key" + 
        " FROM thing, edition_str" +
        " WHERE thing.id=edition_str.thing_id" + 
            " AND key_id=$key_id" +
            " AND value=$value" +
        " ORDER BY thing.last_modified LIMIT 10",
        vars=locals())
    return [row.key for row in rows]

def get(key):
    # try memcache
    memcache = get_memcache()
    if memcache:
        json = memcache.get(key)
        if json:
            return simplejson.loads(json)

    # try db
    db = get_db()
    try:
        thing = db.query("SELECT * FROM thing WHERE key=$key", vars=locals())[0]
        data = db.query("SELECT * FROM data WHERE data.thing_id=$thing.id AND data.revision=$thing.latest_revision", vars=locals())[0]
        return simplejson.loads(data.data)
    except IndexError:
        return None