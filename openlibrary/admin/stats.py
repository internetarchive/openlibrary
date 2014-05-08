"""
Script to read out data from thingdb and put it in couch so that it
can be queried by the /admin pages on openlibrary
"""


import os
import logging
import datetime

import web
import yaml
import couchdb

import numbers


web.config.debug = False

class InvalidType(TypeError): pass

def connect_to_pg(config_file):
    """Connects to the postgres database specified in the dictionary
    `config`. Needs a top level key `db_parameters` and under that
    `database` (or `db`) at the least. If `user` and `host` are
    provided, they're used as well."""
    f = open(config_file)
    config = yaml.load(f)
    f.close()
    conf = {}
    conf["db"] = config["db_parameters"].get("database") or config["db_parameters"].get("db")
    if not conf['db']:
        raise KeyError("database/db")
    host = config["db_parameters"].get("host")
    user = config["db_parameters"].get("user") or config["db_parameters"].get("username")
    if host:
        conf["host"] = host
    if user:
        conf["user"] = user
    logging.debug(" Postgres Database : %(db)s"%conf)
    return web.database(dbn="postgres",**conf)


def connect_to_couch(config_file):
    "Connects to the couch databases"
    f = open(config_file)
    config = yaml.load(f)
    f.close()
    admin_db = config["admin"]["counts_db"]
    editions_db = config["lists"]["editions_db"]
    works_db = config["lists"]["works_db"]
    seeds_db = config["lists"]["seeds_db"]
    logging.debug(" Admin Database is %s", admin_db)
    logging.debug(" Editions Database is %s", editions_db)
    logging.debug(" Works Database is %s", works_db)
    logging.debug(" Seeds Database is %s", seeds_db)
    return couchdb.Database(admin_db), couchdb.Database(editions_db), couchdb.Database(works_db), couchdb.Database(seeds_db)

def get_config_info(infobase_config):
    """Parses the config file(s) to get back all the necessary pieces of data.

    Add extra parameters here and change the point of calling.
    """
    f = open(infobase_config)
    config = yaml.load(f)
    f.close()
    logroot = config.get("writelog")
    return logroot
    
def store_data(db, data, date):
    uid = "counts-%s"%date
    logging.debug(" Updating admin_db for %s - %s", uid, data)
    try:
        vals = db[uid]
        vals.update(data)
    except couchdb.http.ResourceNotFound:
        vals = data
        db[uid] = vals
    db.save(vals)

    # start storing data in store as well, so that we can phase out couch
    doc = web.ctx.site.store.get(uid) or {}
    doc.update(data)
    doc['type'] = 'admin-stats'
    web.ctx.site.store[uid] = doc

def run_gathering_functions(infobase_db, coverstore_db, seeds_db, editions_db, works_db, admin_db,
                            start, end, logroot, prefix, key_prefix = None):
    """Runs all the data gathering functions with the given prefix
    inside the numbers module"""
    funcs = [x for x in dir(numbers) if x.startswith(prefix)]
    d = {}
    for i in funcs:
        fn = getattr(numbers, i)
        key = i.replace(prefix,"")
        if key_prefix:
            key = "%s_%s"% (key_prefix, key)
        try:
            ret = fn(thingdb     = infobase_db,
                     coverdb     = coverstore_db,
                     seeds_db    = seeds_db,
                     editions_db = editions_db,
                     works_db    = works_db,
                     admin_db    = admin_db,
                     logroot     = logroot,
                     start       = start,
                     end         = end)
            logging.info("  %s - %s", i, ret)
            d[key] = ret
        except numbers.NoStats:
            logging.warning("  %s - No statistics available", i)
        except Exception, k:
            logging.warning("  Failed with %s", k)
    return d

def setup_ol_config(openlibrary_config_file):
    """Setup OL configuration.

    Required for storing counts in store.
    """
    import infogami
    from infogami import config
    from infogami.utils import delegate

    config.plugin_path += ['openlibrary.plugins']
    config.site = "openlibrary.org"

    infogami.load_config(openlibrary_config_file)
    infogami.config.infobase_parameters = dict(type="ol")

    if config.get("infobase_config_file"):
        dir = os.path.dirname(openlibrary_config_file)
        path = os.path.join(dir, config.infobase_config_file)
        config.infobase = yaml.safe_load(open(path).read())

    infogami._setup()

def main(infobase_config, openlibrary_config, coverstore_config, ndays = 1):
    logging.basicConfig(level=logging.DEBUG, format = "%(levelname)-8s : %(filename)-12s:%(lineno)4d : %(message)s")
    logging.info("Parsing config file")
    try:
        infobase_db = connect_to_pg(infobase_config)
        coverstore_db = connect_to_pg(coverstore_config)
        admin_db, editions_db, works_db, seeds_db = connect_to_couch(openlibrary_config)
        logroot = get_config_info(infobase_config)
    except KeyError,k:
        logging.critical("Config file section '%s' missing", k.args[0])
        return -1

    setup_ol_config(openlibrary_config)

    # Gather delta and total counts
    # Total counts are simply computed and updated for the current day
    # Delta counts are computed by subtracting the current total from yesterday's total
    today = datetime.datetime.now()
    yesterday = today - datetime.timedelta(days = 1)
    data = {}
    logging.info("Gathering total data")
    data.update(run_gathering_functions(infobase_db, coverstore_db, seeds_db, editions_db, works_db, admin_db,
                                        yesterday, today, logroot,
                                        prefix = "admin_total__", key_prefix = "total"))
    logging.info("Gathering data using difference between totals")
    data.update(run_gathering_functions(infobase_db, coverstore_db, seeds_db, editions_db, works_db, admin_db,
                                        yesterday, today, logroot,
                                        prefix = "admin_delta__"))
    store_data(admin_db, data, today.strftime("%Y-%m-%d"))
    # Now gather data which can be queried based on date ranges
    # The queries will be from the beginning of today till right now
    # The data will be stored as the counts of the current day.
    end = datetime.datetime.now() # Right now
    start = datetime.datetime(hour = 0, minute = 0, second = 0, day = end.day, month = end.month, year = end.year) # Beginning of the day
    logging.info("Gathering range data")
    data = {}
    for i in range(int(ndays)):
        logging.info(" %s to %s", start, end)
        data.update(run_gathering_functions(infobase_db, coverstore_db, seeds_db, editions_db, works_db, admin_db,
                                            start, end, logroot,
                                            prefix = "admin_range__"))
        store_data(admin_db, data, start.strftime("%Y-%m-%d"))
        end = start
        start = end - datetime.timedelta(days = 1)
    if numbers.sqlitefile:
        logging.info("Removing sqlite file used for ipstats")
        os.unlink(numbers.sqlitefile)
    return 0
