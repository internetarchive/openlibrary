"""
Script to read out data from thingdb and put it in couch so that it
can be queried by the /admin pages on openlibrary
"""

import datetime
import logging
import os

import web
import yaml

from openlibrary.admin import numbers

logger = logging.getLogger(__name__)


web.config.debug = False


class InvalidType(TypeError):
    pass


def connect_to_pg(config_file):
    """Connects to the postgres database specified in the dictionary
    `config`. Needs a top level key `db_parameters` and under that
    `database` (or `db`) at the least. If `user` and `host` are
    provided, they're used as well."""
    with open(config_file) as f:
        config = yaml.safe_load(f)
    conf = {}
    conf["db"] = config["db_parameters"].get("database") or config["db_parameters"].get(
        "db"
    )
    if not conf['db']:
        raise KeyError("database/db")
    host = config["db_parameters"].get("host")
    user = config["db_parameters"].get("user") or config["db_parameters"].get(
        "username"
    )
    if host:
        conf["host"] = host
    if user:
        conf["user"] = user
    logger.debug(" Postgres Database : %(db)s" % conf)
    return web.database(dbn="postgres", **conf)


def get_config_info(infobase_config):
    """Parses the config file(s) to get back all the necessary pieces of data.

    Add extra parameters here and change the point of calling.
    """
    with open(infobase_config) as f:
        config = yaml.safe_load(f)
    logroot = config.get("writelog")
    return logroot


def store_data(data, date):
    uid = "counts-%s" % date
    logger.debug(" Updating stats for %s - %s", uid, data)
    doc = web.ctx.site.store.get(uid) or {}
    doc.update(data)
    doc['type'] = 'admin-stats'
    # as per https://github.com/internetarchive/infogami/blob/master/infogami/infobase/_dbstore/store.py#L79-L83
    # avoid document collisions if multiple tasks updating stats in competition (race)
    doc["_rev"] = None
    web.ctx.site.store[uid] = doc


def run_gathering_functions(
    infobase_db, coverstore_db, start, end, logroot, prefix, key_prefix=None
):
    """Runs all the data gathering functions with the given prefix
    inside the numbers module"""
    funcs = [x for x in dir(numbers) if x.startswith(prefix)]
    d = {}
    for i in funcs:
        fn = getattr(numbers, i)
        key = i.replace(prefix, "")
        if key_prefix:
            key = f"{key_prefix}_{key}"
        try:
            ret = fn(
                thingdb=infobase_db,
                coverdb=coverstore_db,
                logroot=logroot,
                start=start,
                end=end,
            )
            logger.info("  %s - %s", i, ret)
            d[key] = ret
        except numbers.NoStats:
            logger.warning("  %s - No statistics available", i)
        except Exception as k:
            logger.warning("  Failed with %s", k)
    return d


def setup_ol_config(openlibrary_config_file):
    """Setup OL configuration.

    Required for storing counts in store.
    """
    import infogami  # noqa: PLC0415
    from infogami import config  # noqa: PLC0415

    config.plugin_path += ['openlibrary.plugins']
    config.site = "openlibrary.org"

    infogami.load_config(openlibrary_config_file)
    infogami.config.infobase_parameters = {"type": "ol"}

    if config.get("infobase_config_file"):
        dir = os.path.dirname(openlibrary_config_file)
        path = os.path.join(dir, config.infobase_config_file)
        with open(path) as file:
            config.infobase = yaml.safe_load(file)

    infogami._setup()


def main(infobase_config, openlibrary_config, coverstore_config, ndays=1):
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)-8s : %(filename)-12s:%(lineno)4d : %(message)s",
    )
    logger.info("Parsing config file")
    try:
        infobase_db = connect_to_pg(infobase_config)
        coverstore_db = connect_to_pg(coverstore_config)
        logroot = get_config_info(infobase_config)
    except KeyError as k:
        logger.critical("Config file section '%s' missing", k.args[0])
        return -1

    setup_ol_config(openlibrary_config)

    # Gather delta and total counts
    # Total counts are simply computed and updated for the current day
    # Delta counts are computed by subtracting the current total from yesterday's total
    today = datetime.datetime.now()
    yesterday = today - datetime.timedelta(days=1)
    data = {}

    logger.info("Gathering total data")
    data.update(
        run_gathering_functions(
            infobase_db,
            coverstore_db,
            yesterday,
            today,
            logroot,
            prefix="admin_total__",
            key_prefix="total",
        )
    )
    logger.info("Gathering data using difference between totals")
    data.update(
        run_gathering_functions(
            infobase_db,
            coverstore_db,
            yesterday,
            today,
            logroot,
            prefix="admin_delta__",
        )
    )
    store_data(data, today.strftime("%Y-%m-%d"))
    # Now gather data which can be queried based on date ranges
    # The queries will be from the beginning of today till right now
    # The data will be stored as the counts of the current day.
    end = datetime.datetime.now()  # - datetime.timedelta(days = 10)# Right now
    start = datetime.datetime(
        hour=0, minute=0, second=0, day=end.day, month=end.month, year=end.year
    )  # Beginning of the day
    logger.info("Gathering range data")
    data = {}
    for i in range(int(ndays)):
        logger.info(" %s to %s", start, end)
        data.update(
            run_gathering_functions(
                infobase_db, coverstore_db, start, end, logroot, prefix="admin_range__"
            )
        )
        store_data(data, start.strftime("%Y-%m-%d"))
        end = start
        start = end - datetime.timedelta(days=1)
    return 0
