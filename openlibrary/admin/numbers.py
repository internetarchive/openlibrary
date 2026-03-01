"""
List of functions that return various numbers which are stored in the
admin database by the stats module.

All functions prefixed with `admin_range__` will be run for each day and the
result will be stored as the part after it. e.g. the result of
admin_range__foo will be stored under the key `foo`.

All functions prefixed with `admin_total__` will be run for the current
day and the result will be stored as `total_<key>`. e.g. the result of
`admin_total__foo` will be stored under the key `total_foo`.

Functions with names other than the these will not be called from the
main harness. They can be utility functions.

"""

import functools
import logging

logger = logging.getLogger(__name__)


class InvalidType(TypeError):
    pass


class NoStats(TypeError):
    pass


# Utility functions
def query_single_thing(db, typ, start, end):
    "Query the counts a single type from the things table"
    q1 = "SELECT id as id from thing where key=$typ"
    typ = f'/type/{typ}'
    result = db.query(q1, vars=locals())
    try:
        kid = result[0].id
    except IndexError:
        raise InvalidType(f"No id for type '/type/{typ} in the database")

    q2 = "SELECT count(*) as count FROM thing WHERE type=$type_id AND created >= $start_date AND created < $end_date"
    result = db.query(q2, vars={'type_id': kid, 'start_date': start, 'end_date': end})

    count = result[0].count
    return count


def single_thing_skeleton(**kargs):
    """Returns number of things of `type` added between `start` and `end`.

    `type` is partially applied for admin__[work, edition, user, author, list].
    """
    try:
        typ = kargs['type']
        start = kargs['start'].strftime("%Y-%m-%d")
        end = kargs['end'].strftime("%Y-%m-%d %H:%M:%S")
        db = kargs['thingdb']
    except KeyError as k:
        raise TypeError(f"{k} is a required argument for admin_range__{typ}")
    return query_single_thing(db, typ, start, end)


cached_bot_accounts = None


def get_bot_accounts(thingdb=None) -> list[int]:
    """
    Returns a list of all `thing` table IDs that are associated with
    bot accounts.
    """
    bot_query = """
        SELECT id
        FROM thing
        WHERE key IN (
          SELECT REPLACE(key, 'account/', '/people/')
          FROM store
          WHERE id IN (
            SELECT store_id
            FROM store_index
            WHERE type = 'account'
              AND name = 'bot'
              AND value <> 'false'
          )
        )
    """
    oldb = thingdb
    return [item.get('id') for item in list(oldb.query(bot_query))]


def _get_cached_bot_accounts(thingdb=None) -> list[int]:
    """
    Returns a list of `thing` table IDs that are associated with
    bot accounts.

    Results are cached in the global `cached_bot_accounts`
    variable.  If this variable is not set, the `get_bot_accounts`
    function is used to fetch these identifiers.
    """
    global cached_bot_accounts
    if cached_bot_accounts is None:
        cached_bot_accounts = get_bot_accounts(thingdb=thingdb)
    return cached_bot_accounts


# Public functions that are used by stats.py
def admin_range__human_edits(**kargs):
    """Calculates the number of edit actions performed by humans
    between the given `start` and `end` dates. `thingdb` is the database.
    """
    try:
        start = kargs['start'].strftime("%Y-%m-%d")
        end = kargs['end'].strftime("%Y-%m-%d %H:%M:%S")
        db = kargs['thingdb']
    except KeyError as k:
        raise TypeError(f"{k} is a required argument for admin_range__human_edits")
    bot_ids = _get_cached_bot_accounts(thingdb=kargs['thingdb'])
    q1 = (
        "SELECT count(t.id) AS count FROM transaction t WHERE "
        "t.created >= $start and t.created < $end AND "
        "t.author_id NOT IN $bot_ids"
    )
    result = db.query(q1, vars={'bot_ids': bot_ids, 'start': start, 'end': end})
    count = result[0].count
    return count


def admin_range__bot_edits(**kargs):
    """Calculates the number of edit actions performed by bots between
    the `start` and `end` dates. `thingdb` is the database.
    """
    try:
        start = kargs['start'].strftime("%Y-%m-%d")
        end = kargs['end'].strftime("%Y-%m-%d %H:%M:%S")
        db = kargs['thingdb']
    except KeyError as k:
        raise TypeError(f"{k} is a required argument for admin_range__bot_edits")
    bot_ids = _get_cached_bot_accounts(thingdb=kargs['thingdb'])
    q1 = (
        "SELECT count(t.id) AS count FROM transaction t WHERE "
        "t.created >= $start and t.created < $end AND "
        "t.author_id IN $bot_ids"
    )
    result = db.query(q1, vars={'bot_ids': bot_ids, 'start': start, 'end': end})
    count = result[0].count
    return count


def admin_range__covers(**kargs):
    "Queries the number of covers added between `start` and `end`"
    try:
        start = kargs['start'].strftime("%Y-%m-%d")
        end = kargs['end'].strftime("%Y-%m-%d %H:%M:%S")
        db = kargs['coverdb']
    except KeyError as k:
        raise TypeError(f"{k} is a required argument for admin_range__covers")
    q1 = f"SELECT count(*) as count from cover where created>= '{start}' and created < '{end}'"
    result = db.query(q1)
    count = result[0].count
    return count


admin_range__works = functools.partial(single_thing_skeleton, type="work")
admin_range__editions = functools.partial(single_thing_skeleton, type="edition")
admin_range__authors = functools.partial(single_thing_skeleton, type="author")
admin_range__lists = functools.partial(single_thing_skeleton, type="list")
admin_range__members = functools.partial(single_thing_skeleton, type="user")


def admin_range__loans(**kargs):
    """Finds the number of loans on a given day.

    Loan info is written to the `stats` table.  Such entries will have
    type `loan`.  As of writing, _only_ loan data is saved in the `stats`
    table.
    """
    try:
        db = kargs['thingdb']
        start = kargs['start']
        end = kargs['end']
    except KeyError as k:
        raise TypeError(f"{k} is a required argument for admin_total__ebooks")
    result = db.query(
        "SELECT count(*) as count FROM stats"
        " WHERE type='loan'"
        "   AND created >= $start"
        "   AND created < $end",
        vars=locals(),
    )
    return result[0].count


def admin_total__authors(**kargs):
    db = kargs['thingdb']
    return _count_things(db, "/type/author")


def admin_total__lists(**kargs):
    try:
        db = kargs['thingdb']
    except KeyError as k:
        raise TypeError(f"{k} is a required argument for admin_total__lists")
    # Computing total number of lists
    q1 = "SELECT id as id from thing where key='/type/list'"
    result = db.query(q1)
    try:
        kid = result[0].id
    except IndexError:
        raise InvalidType("No id for type '/type/list' in the database")
    q2 = "select count(*) as count from thing where type=%d" % kid
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
    result = db.query(
        "SELECT count(*) as count FROM thing WHERE type=$type_id", vars=locals()
    )
    return result[0].count


def _query_count(db, table, type, property, distinct=False):
    type_id = db.where("thing", key=type)[0].id
    key_id = db.where('property', type=type_id, name=property)[0].id
    if distinct:
        what = 'count(distinct(thing_id)) as count'
    else:
        what = 'count(thing_id) as count'
    result = db.select(
        table, what=what, where='key_id=$key_id', vars={"key_id": key_id}
    )
    return result[0].count


def admin_total__members(**kargs):
    db = kargs['thingdb']
    return _count_things(db, '/type/user')
