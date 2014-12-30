"""
List of functions that return various numbers which are stored in the
admin database by the stats module.

All functions prefixed with `admin_range__` will be run for each day and the
result will be stored as the part after it. e.g. the result of
admin_range__foo will be stored under the key `foo`.

All functions prefixed with `admin_delta__` will be run for the current
day and the result will be stored as the part after it. e.g. the
result of `admin_delta__foo` will be stored under the key `foo`.

All functions prefixed with `admin_total__` will be run for the current
day and the result will be stored as `total_<key>`. e.g. the result of
`admin_total__foo` will be stored under the key `total__foo`.

Functions with names other than the these will not be called from the
main harness. They can be utility functions.

"""
import os
import time
import urllib
import logging
import tempfile
import datetime
import calendar
import functools

import web
import couchdb

logger = logging.getLogger(__name__)

class InvalidType(TypeError): pass
class NoStats(TypeError): pass

sqlitefile = None

# Utility functions
def query_single_thing(db, typ, start, end):
    "Query the counts a single type from the things table"
    q1 = "SELECT id as id from thing where key=$typ"
    typ = '/type/%s'%typ
    result = db.query(q1, vars=locals())
    try:
        kid = result[0].id 
    except IndexError:
        raise InvalidType("No id for type '/type/%s in the datbase"%typ)
    q2 = "select count(*) as count from thing where type=%d and created >= '%s' and created < '%s'"% (kid, start, end)
    result = db.query(q2)
    count = result[0].count
    return count


def single_thing_skeleton(**kargs):
    """Returns number of things of `type` added between `start` and `end`.

    `type` is partially applied for admin__[work, edition, user, author, list].
    """
    try:
        typ   = kargs['type']
        start = kargs['start'].strftime("%Y-%m-%d")
        end   = kargs['end'].strftime("%Y-%m-%d %H:%M:%S")
        db    = kargs['thingdb']
    except KeyError, k:
        raise TypeError("%s is a required argument for admin_range__%s"%(k, typ))
    return query_single_thing(db, typ, start, end)
    

# Public functions that are used by stats.py
def admin_range__human_edits(**kargs):
    """Calculates the number of edits between the `start` and `end`
    parameters done by humans. `thingdb` is the database.
    """
    try:
        start = kargs['start'].strftime("%Y-%m-%d")
        end   = kargs['end'].strftime("%Y-%m-%d %H:%M:%S")
        db    = kargs['thingdb']
    except KeyError, k:
        raise TypeError("%s is a required argument for admin_range__human_edits"%k)
    q1 = "SELECT count(*) AS count FROM transaction WHERE created >= '%s' and created < '%s'"% (start, end)
    result = db.query(q1)
    total_edits = result[0].count
    q1 = "SELECT count(DISTINCT t.id) AS count FROM transaction t, version v WHERE v.transaction_id=t.id AND t.created >= '%s' and t.created < '%s' AND t.author_id IN (SELECT thing_id FROM account WHERE bot = 't')"% (start, end)
    result = db.query(q1)
    bot_edits = result[0].count
    return total_edits - bot_edits

def admin_range__bot_edits(**kargs):
    """Calculates the number of edits between the `start` and `end`
    parameters done by bots. `thingdb` is the database.
    """
    try:
        start = kargs['start'].strftime("%Y-%m-%d")
        end   = kargs['end'].strftime("%Y-%m-%d %H:%M:%S")
        db    = kargs['thingdb']
    except KeyError, k:
        raise TypeError("%s is a required argument for admin_range__bot_edits"%k)
    q1 = "SELECT count(*) AS count FROM transaction t, version v WHERE v.transaction_id=t.id AND t.created >= '%s' and t.created < '%s' AND t.author_id IN (SELECT thing_id FROM account WHERE bot = 't')"% (start, end)
    result = db.query(q1)
    count = result[0].count
    return count
    

def admin_range__covers(**kargs):
    "Queries the number of covers added between `start` and `end`"
    try:
        start = kargs['start'].strftime("%Y-%m-%d")
        end   = kargs['end'].strftime("%Y-%m-%d %H:%M:%S")
        db    = kargs['coverdb']
    except KeyError, k:
        raise TypeError("%s is a required argument for admin_range__covers"%k)
    q1 = "SELECT count(*) as count from cover where created>= '%s' and created < '%s'"% (start, end)
    result = db.query(q1)
    count = result[0].count
    return count


admin_range__works    = functools.partial(single_thing_skeleton, type="work")
admin_range__editions = functools.partial(single_thing_skeleton, type="edition")
admin_range__users    = functools.partial(single_thing_skeleton, type="user")
admin_range__authors  = functools.partial(single_thing_skeleton, type="author")
admin_range__lists    = functools.partial(single_thing_skeleton, type="list")
admin_range__members  = functools.partial(single_thing_skeleton, type="user")

def admin_range__visitors(**kargs):
    "Finds number of unique IPs to visit the OL website."
    try:
        date = kargs['start']
    except KeyError, k:
        raise TypeError("%s is a required argument for admin_range__visitors"%k)
    global sqlitefile
    if not sqlitefile:
        sqlitefile = tempfile.mktemp(prefix="sqlite-")
        url = "http://www.archive.org/download/stats/numUniqueIPsOL.sqlite"
        logging.debug("  Downloading '%s'", url)
        sqlite_contents = urllib.urlopen(url).read()
        f = open(sqlitefile, "w")
        f.write(sqlite_contents)
        f.close()
    db = web.database(dbn="sqlite", db = sqlitefile)
    d = date.replace(hour = 0, minute = 0, second = 0, microsecond = 0)
    key = calendar.timegm(d.timetuple())
    q = "SELECT value AS count FROM data WHERE timestamp = %d"%key
    result = list(db.query(q))
    if result:
        return result[0].count
    else:
        logging.debug("  No statistics obtained for %s (%d)", date, key)
        raise NoStats("No record for %s"%date)
    
def admin_range__loans(**kargs):
    """Finds the number of loans on a given day.

    Loan info is written to infobase write log. Grepping through the log file gives us the counts.
    
    WARNING: This script must be run on the node that has infobase logs.
    """
    try:
        db = kargs['thingdb']        
        start = kargs['start']
        end = kargs['end']
    except KeyError, k:
        raise TypeError("%s is a required argument for admin_total__ebooks"%k)
    result = db.query(
        "SELECT count(*) as count FROM stats" +
        " WHERE type='loan'" +
        "   AND created >= $start" + 
        "   AND created < $end",
        vars=locals())
    return result[0].count

def admin_total__authors(**kargs):
    db = kargs['thingdb']
    return _count_things(db, "/type/author")

def admin_total__subjects(**kargs):
    # Anand - Dec 2014 - TODO
    # Earlier implementation that uses couchdb is gone now
    return 0


def admin_total__lists(**kargs):
    try:
        db    = kargs['thingdb']
    except KeyError, k:
        raise TypeError("%s is a required argument for admin_total__lists"%k)    
    # Computing total number of lists
    q1 = "SELECT id as id from thing where key='/type/list'"
    result = db.query(q1)
    try:
        kid = result[0].id 
    except IndexError:
        raise InvalidType("No id for type '/type/list' in the database")
    q2 = "select count(*) as count from thing where type=%d"% kid
    result = db.query(q2)
    total_lists = result[0].count
    return total_lists


def admin_total__covers(**kargs):
    db = kargs['coverdb']
    return db.query("SELECT count(*) as count FROM cover")[0].count

def admin_total__works(**kargs):
    db = kargs['thingdb']
    return _count_things(db, '/type/work')

def admin_total__editions(**kargs):
    db = kargs['thingdb']
    return _count_things(db, '/type/edition')

def _count_things(db, type):
    type_id = db.where("thing", key=type)[0].id
    result = db.query("SELECT count(*) as count FROM thing WHERE type=$type_id", vars=locals())
    return result[0].count

def _query_count(db, table, type, property, distinct=False):
    key_id = db.where(table, type=type, name=property)[0].id
    if distinct:
        what = 'count(distinct(thing_id)) as count'
    else:
        what = 'count(thing_id) as count'
    result = db.select(table, what, where='key_id=$key_id', vars=dict(key_id=key_id))
    return result[0].count

def admin_total__ebooks(**kargs):
    db = kargs['thingdb']
    return _query_count(db, "edition_str", "/type/edition", "ocaid")

def admin_total__members(**kargs):
    db = kargs['thingdb']
    return _count_things(db, '/type/user')

def admin_delta__ebooks(**kargs):
    # Anand - Dec 2014 - TODO
    # Earlier implementation that uses couchdb is gone now
    return 0

def admin_delta__subjects(**kargs):
    # Anand - Dec 2014 - TODO
    # Earlier implementation that uses couchdb is gone now
    return 0