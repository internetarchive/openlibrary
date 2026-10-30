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
from datetime import timedelta

import web

logger = logging.getLogger(__name__)


class InvalidType(TypeError):
    pass


class NoStats(TypeError):
    pass


# Utility functions
def query_single_thing(db, typ, start, end):
    "Query the counts a single type from the things table"
    q1 = "SELECT id as id from thing where key=$typ"
    typ = f"/type/{typ}"
    result = db.query(q1, vars=locals())
    try:
        kid = result[0].id
    except IndexError:
        raise InvalidType(f"No id for type '/type/{typ} in the database")

    q2 = "SELECT count(*) as count FROM thing WHERE type=$type_id AND created >= $start_date AND created < $end_date"
    result = db.query(q2, vars={"type_id": kid, "start_date": start, "end_date": end})

    count = result[0].count
    return count


def single_thing_skeleton(**kargs):
    """Returns number of things of `type` added between `start` and `end`.

    `type` is partially applied for admin__[work, edition, user, author, list].
    """
    try:
        typ = kargs["type"]
        start = kargs["start"].strftime("%Y-%m-%d")
        end = kargs["end"].strftime("%Y-%m-%d %H:%M:%S")
        db = kargs["thingdb"]
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
    return [item.get("id") for item in list(oldb.query(bot_query))]


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
def _count_transactions(db, start, end, where="", **vars):
    "Transactions between `start` and `end`, narrowed by `where` (an SQL fragment using `vars`)."
    sql = f"SELECT count(t.id) AS count FROM transaction t WHERE t.created >= $start and t.created < $end{where}"
    return db.query(sql, vars={"start": start, "end": end, **vars})[0].count


def _range_args(fn_name, kargs):
    try:
        return kargs["thingdb"], kargs["start"].strftime("%Y-%m-%d"), kargs["end"].strftime("%Y-%m-%d %H:%M:%S")
    except KeyError as k:
        raise TypeError(f"{k} is a required argument for {fn_name}")


def admin_range__human_edits(**kargs):
    "Transactions by non-bot accounts between `start` and `end`, signups and all. See `admin_range__catalog_edits`."
    db, start, end = _range_args("admin_range__human_edits", kargs)
    bot_ids = _get_cached_bot_accounts(thingdb=db)
    return _count_transactions(db, start, end, " AND t.author_id NOT IN $bot_ids", bot_ids=bot_ids)


def admin_range__bot_edits(**kargs):
    "Transactions by bot accounts between `start` and `end`."
    db, start, end = _range_args("admin_range__bot_edits", kargs)
    bot_ids = _get_cached_bot_accounts(thingdb=db)
    return _count_transactions(db, start, end, " AND t.author_id IN $bot_ids", bot_ids=bot_ids)


# Transactions that aren't edits to the catalog. Every signup writes a `new-account`
# transaction, and at ~10k signups a day they outnumber real edits several times over.
NON_EDIT_ACTIONS = (
    "new-account",
    "register",
    "create-stats",
    "edit-blocked-ips",
    "edit-usergroup-add-member",
    "edit-usergroup-delete-member",
    "bulk-edit-permissions",
)


def admin_range__catalog_edits(**kargs):
    """Human edits that change the catalog: `admin_range__human_edits` without signups and admin
    housekeeping. A separate key so the daily docs written before it existed keep their meaning."""
    db, start, end = _range_args("admin_range__catalog_edits", kargs)
    bot_ids = _get_cached_bot_accounts(thingdb=db)
    return _count_transactions(
        db, start, end, " AND t.action NOT IN $non_edit_actions AND t.author_id NOT IN $bot_ids", bot_ids=bot_ids, non_edit_actions=NON_EDIT_ACTIONS
    )


# Someone making or changing a list; `edit-list-seeds` is a save of what's on it.
LIST_EDIT_ACTIONS = ("create-list", "edit-list-seeds")


def admin_range__list_edits(**kargs):
    "Counts lists created or edited between `start` and `end`."
    db, start, end = _range_args("admin_range__list_edits", kargs)
    return _count_transactions(db, start, end, " AND t.action IN $list_edit_actions", list_edit_actions=LIST_EDIT_ACTIONS)


# A changeset that touches a book, work or author record, whatever its action name.
CATALOG_CHANGE = '"/(books|works|authors)/OL'
# `data.source` on Tasks saves; matches `openlibrary.contribute.save.SOURCE`. Infogami indexes it in `transaction_index`.
TASKS_SOURCE = "contribute"


def _window_args(fn_name, kargs, days):
    """The `days` before `end`: rolling windows, since distinct editors don't add up across days.

    `days=1` is the calendar day the gatherer hands in as `start`..`end`, like the other daily keys. For today's hourly
    run that is midnight to now; a window ending at `end` would be the last 24 hours instead, and a bar per day would
    double-count the evening before."""
    if days == 1:
        return _range_args(fn_name, kargs)
    try:
        db, end = kargs["thingdb"], kargs["end"]
    except KeyError as k:
        raise TypeError(f"{k} is a required argument for {fn_name}")
    return db, (end - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def _count_editors(db, since, end, where="", **vars):
    "Signed-in, non-bot accounts with a catalog change between `since` and `end`, narrowed by `where`."
    # `NOT IN ()` is a syntax error, and a dev database may have no bots.
    bot_ids = _get_cached_bot_accounts(thingdb=db)
    not_bot = " AND t.author_id NOT IN $bot_ids" if bot_ids else ""
    sql = f"""
        WITH editors AS (
            SELECT DISTINCT t.author_id FROM transaction t
            WHERE t.created >= $since AND t.created < $end AND t.author_id IS NOT NULL{not_bot} AND t.changes ~ $catalog_change
        )
        SELECT count(*) AS count FROM editors e WHERE true{where}
    """
    vars = {"since": since, "end": end, "bot_ids": bot_ids, "catalog_change": CATALOG_CHANGE, **vars}
    return db.query(sql, vars=vars)[0].count


def catalog_editors(days, **kargs):
    "Accounts that changed a catalog record in the `days` before `end`."
    db, since, end = _window_args(f"admin_range__catalog_editors_{days}d", kargs, days)
    return _count_editors(db, since, end)


def new_catalog_editors(days, **kargs):
    "Of `catalog_editors`, those whose first catalog change ever falls in the window."
    db, since, end = _window_args(f"admin_range__new_catalog_editors_{days}d", kargs, days)
    earlier = " AND NOT EXISTS (SELECT 1 FROM transaction p WHERE p.author_id = e.author_id AND p.created < $since AND p.changes ~ $catalog_change)"
    return _count_editors(db, since, end, earlier)


TASKS_SAVES = "SELECT tx_id FROM transaction_index WHERE key = 'source' AND value = $tasks_source"


def tasks_editors(days, **kargs):
    "Accounts that saved from the Tasks page in the `days` before `end`."
    db, since, end = _window_args(f"admin_range__tasks_editors_{days}d", kargs, days)
    sql = f"SELECT count(DISTINCT t.author_id) AS count FROM transaction t WHERE t.created >= $since AND t.created < $end AND t.id IN ({TASKS_SAVES})"
    return db.query(sql, vars={"since": since, "end": end, "tasks_source": TASKS_SOURCE})[0].count


def tasks_saves(days, **kargs):
    "Saves made from the Tasks page in the `days` before `end`."
    db, since, end = _window_args(f"admin_range__tasks_saves_{days}d", kargs, days)
    return _count_transactions(db, since, end, f" AND t.id IN ({TASKS_SAVES})", tasks_source=TASKS_SOURCE)


# The `_1d` keys are what a bar-per-day chart plots; the 7d and 28d windows stay for the headline numbers, and a
# week or month view samples them at the end of each period.
admin_range__catalog_editors_1d = functools.partial(catalog_editors, 1)
admin_range__catalog_editors_7d = functools.partial(catalog_editors, 7)
admin_range__catalog_editors_28d = functools.partial(catalog_editors, 28)
admin_range__new_catalog_editors_1d = functools.partial(new_catalog_editors, 1)
admin_range__new_catalog_editors_7d = functools.partial(new_catalog_editors, 7)
admin_range__new_catalog_editors_28d = functools.partial(new_catalog_editors, 28)
admin_range__tasks_editors_1d = functools.partial(tasks_editors, 1)
admin_range__tasks_editors_7d = functools.partial(tasks_editors, 7)
admin_range__tasks_editors_28d = functools.partial(tasks_editors, 28)
admin_range__tasks_saves_1d = functools.partial(tasks_saves, 1)
admin_range__tasks_saves_28d = functools.partial(tasks_saves, 28)


def admin_range__tasks_saves_by_field_1d(**kargs):
    "The day's Tasks saves by the field they filled, e.g. `{'number_of_pages': 7, 'covers': 2}`. Stored as a dict."
    db, start, end = _range_args("admin_range__tasks_saves_by_field_1d", kargs)
    sql = f"""
        SELECT t.data::json->>'field' AS field, count(*) AS count FROM transaction t
        WHERE t.created >= $start AND t.created < $end AND t.id IN ({TASKS_SAVES})
        GROUP BY 1
    """
    rows = db.query(sql, vars={"start": start, "end": end, "tasks_source": TASKS_SOURCE})
    return {row.field: row.count for row in rows if row.field}


# Initiative counts. The frozen edition list and the not-found marks live in the store, so these read through
# `web.ctx.site`, which `stats.setup_ol_config` provides, rather than through `thingdb`.
_cached_initiative_progress: dict | None = None


def _initiative():
    from openlibrary.contribute import initiatives

    return initiatives


def _initiative_progress(kargs) -> dict:
    """`initiatives.progress` for the active initiative, as of now. Only for today: a snapshot has no history, and the
    backfill loop would otherwise stamp today's figure onto every past day. Read once per run, for all four keys.
    Never picks the list: freezing it is the web app's job, so until it has, there's nothing to report."""
    global _cached_initiative_progress
    try:
        start, end = kargs["start"], kargs["end"]
    except KeyError as k:
        raise TypeError(f"{k} is a required argument for the initiative counts")
    # Only the run's first window, which ends at "now", is shorter than a day. Checking the clock instead would
    # skip the snapshot when a run that started before midnight gets here after it.
    if end - start >= timedelta(days=1):
        raise NoStats
    if _cached_initiative_progress is None:
        initiatives = _initiative()
        if not (picks := initiatives.load_frozen(initiatives.ACTIVE, web.ctx.site)):
            raise NoStats
        _cached_initiative_progress = initiatives.progress(initiatives.gaps_for(picks, web.ctx.site))
    return _cached_initiative_progress


def admin_range__initiative_slug(**kargs):
    "Which initiative the day's `initiative_*` counts describe, so a new list doesn't continue the old one's lines."
    _initiative_progress(kargs)
    return _initiative().ACTIVE.slug


def admin_range__initiative_open_gaps(**kargs):
    "Fields still missing across the active initiative's editions, less those enough people couldn't find."
    return _initiative_progress(kargs)["open"]


def admin_range__initiative_done_editions(**kargs):
    "Editions on the active initiative's list with nothing left to fill."
    return _initiative_progress(kargs)["done"]


def admin_range__initiative_not_found(**kargs):
    "Fields on the active initiative's list that enough people couldn't find."
    return _initiative_progress(kargs)["not_found"]


def admin_range__initiative_editions(**kargs):
    "Editions on the active initiative's list still in the catalog."
    return _initiative_progress(kargs)["total"]


def admin_range__tasks_saves_initiative_1d(**kargs):
    """The day's Tasks saves on editions in the active initiative's frozen list. The list doesn't move, so unlike the
    snapshot keys this one backfills."""
    db, start, end = _range_args("admin_range__tasks_saves_initiative_1d", kargs)
    initiatives = _initiative()
    if not (picks := initiatives.load_frozen(initiatives.ACTIVE, web.ctx.site)):
        raise NoStats
    keys = [key for key, _readers in picks]
    return _count_transactions(db, start, end, f" AND t.id IN ({TASKS_SAVES}) AND t.changes::json->0->>'key' IN $keys", tasks_source=TASKS_SOURCE, keys=keys)


def admin_range__tasks_saves_undone_28d(**kargs):
    """Tasks saves in the 28 days before `end` whose value the record no longer holds, by undo, revert or a later edit.

    Checked against the record as it is when this runs. Merged or deleted records are left out.
    """
    db, since, end = _window_args("admin_range__tasks_saves_undone_28d", kargs, 28)
    sql = f"""
        SELECT count(*) AS count
        FROM transaction t
        JOIN thing th ON th.key = t.changes::json->0->>'key'
        JOIN data saved ON saved.thing_id = th.id AND saved.revision = (t.changes::json->0->>'revision')::int
        JOIN data latest ON latest.thing_id = th.id AND latest.revision = th.latest_revision
        WHERE t.created >= $since AND t.created < $end AND t.id IN ({TASKS_SAVES})
          AND latest.data::jsonb->'type' = saved.data::jsonb->'type'
          AND NOT COALESCE((latest.data::jsonb -> (t.data::json->>'field')) @> (saved.data::jsonb -> (t.data::json->>'field')), false)
    """
    return db.query(sql, vars={"since": since, "end": end, "tasks_source": TASKS_SOURCE})[0].count


def admin_range__covers(**kargs):
    "Queries the number of covers added between `start` and `end`"
    try:
        start = kargs["start"].strftime("%Y-%m-%d")
        end = kargs["end"].strftime("%Y-%m-%d %H:%M:%S")
        db = kargs["coverdb"]
    except KeyError as k:
        raise TypeError(f"{k} is a required argument for admin_range__covers")
    # Match the parameterized form used by sibling admin_range__* helpers in
    # this module (see admin_range__bot_edits). `start`
    # and `end` are derived from `datetime.strftime` so they are not directly
    # user-controllable today, but using `vars=` keeps this consistent with
    # the parameterized convention and removes the f-string footgun if a
    # future caller passes raw input.
    q1 = "SELECT count(*) as count FROM cover WHERE created >= $start AND created < $end"
    result = db.query(q1, vars={"start": start, "end": end})
    count = result[0].count
    return count


admin_range__works = functools.partial(single_thing_skeleton, type="work")
admin_range__editions = functools.partial(single_thing_skeleton, type="edition")
admin_range__authors = functools.partial(single_thing_skeleton, type="author")
admin_range__lists = functools.partial(single_thing_skeleton, type="list")
admin_range__members = functools.partial(single_thing_skeleton, type="user")


def admin_total__authors(**kargs):
    db = kargs["thingdb"]
    return _count_things(db, "/type/author")


def admin_total__lists(**kargs):
    try:
        db = kargs["thingdb"]
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
    db = kargs["coverdb"]
    return db.query("SELECT count(*) as count FROM cover")[0].count


def admin_total__works(**kargs):
    db = kargs["thingdb"]
    return _count_things(db, "/type/work")


def admin_total__editions(**kargs):
    db = kargs["thingdb"]
    return _count_things(db, "/type/edition")


def _count_things(db, type):
    type_id = db.where("thing", key=type)[0].id
    result = db.query("SELECT count(*) as count FROM thing WHERE type=$type_id", vars=locals())
    return result[0].count


def _query_count(db, table, type, property, distinct=False):
    type_id = db.where("thing", key=type)[0].id
    key_id = db.where("property", type=type_id, name=property)[0].id
    if distinct:
        what = "count(distinct(thing_id)) as count"
    else:
        what = "count(thing_id) as count"
    result = db.select(table, what=what, where="key_id=$key_id", vars={"key_id": key_id})
    return result[0].count


def admin_total__members(**kargs):
    db = kargs["thingdb"]
    return _count_things(db, "/type/user")
