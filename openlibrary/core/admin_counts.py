"""
Script to read out data from thingdb and put it in couch so that it
can be queried by the /admin pages on openlibrary
"""

import logging
import datetime

import web
import yaml
import couchdb

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

def get_range_data(infobase_db, coverstore_db, start, end):
    """Returns the number of new records of various types
    between `start` and `end`"""
    def _query_single_thing(db, typ, start, end):
        "Query the counts a single type from the things table"
        q1 = "SELECT id as id from thing where key='/type/%s'"% typ
        result = db.query(q1)
        try:
            kid = result[0].id 
        except IndexError:
            raise InvalidType("No id for type '/type/%s in the datbase"%typ)
        q2 = "select count(*) as count from thing where type=%d and created >= '%s' and created < '%s'"% (kid, start, end)
        result = db.query(q2)
        count = result[0].count
        return count

    def _query_covers(db, start, end):
        "Queries the number of covers added between start and end"
        q1 = "SELECT count(*) as count from cover where created>= '%s' and created < '%s'"% (start, end)
        result = db.query(q1)
        count = result[0].count
        return count

    def _query_transactions(db, start, end):
        "Queries the number of edits between start and end"
        q1 = "SELECT count(*) as count from transaction where created>= '%s' and created < '%s'"% (start, end)
        result = db.query(q1)
        count = result[0].count
        return count
    
    retval = {}
    for typ in "work edition user author list".split():
        retval[typ] = _query_single_thing(infobase_db, typ, start, end)
        logging.debug("  Type : %s - %d", typ, retval[typ])
    retval["edit"]  = _query_transactions(infobase_db, start, end)
    retval["cover"] = _query_covers(coverstore_db, start, end)
    logging.debug("  Type : cover - %d", retval['cover'])
    return retval

def get_delta_data(admin_db, editions_db, seeds_db, today):
    """Returns the number of new records of `types` by calculating the
    difference between yesterdays numbers and todays"""
    retval = dict()
    yesterday = today - datetime.timedelta(days = 1)
    yesterdays_key = yesterday.strftime("counts-%Y-%m-%d")
    # eBooks
    current_total = editions_db.view("admin/ebooks", stale="ok").rows[0].value
    logging.debug("Getting delta counts for ebooks between %s and today", yesterday.strftime("%Y-%m-%d"))
    try:
        last_total = admin_db[yesterdays_key]["total_ebooks"]
    except (couchdb.http.ResourceNotFound, KeyError):
        last_total = 0
    current_count = current_total - last_total
    retval["ebook"] = current_count
    logging.debug(" Type : ebook - %d", retval['ebook'])
    # Subjects
    rows = seeds_db.view("_all_docs", startkey="a", stale="ok", limit=0)
    current_total = rows.total_rows - rows.offset
    logging.debug("Getting delta counts for subjects between %s and today", yesterday.strftime("%Y-%m-%d"))
    try:
        last_total = admin_db[yesterdays_key]["total_subjects"]
    except (couchdb.http.ResourceNotFound, KeyError):
        last_total = 0
    current_count = current_total - last_total
    retval["subject"] = current_count
    logging.debug(" Type : subjects - %d", retval['subject'])
    return retval

def get_total_data(infobase_db, editions_db, works_db, seeds_db):
    """Get total counts for the various items and return them as a
    dictionary"""
    logging.debug("Getting total counts for works, editions and ebooks")
    # Computing total authors
    off1 = seeds_db.view("_all_docs", startkey="/authors", limit=0, stale="ok", limit = 0).offset
    off2 = seeds_db.view("_all_docs", startkey="/authors/Z", limit=0, stale="ok", limit = 0).offset
    total_authors = off2 - off1
    # Computing total subjects
    rows = seeds_db.view("_all_docs", startkey="a", stale="ok", limit = 0)
    total_subjects = rows.total_rows - rows.offset
    # Computing total number of lists
    q1 = "SELECT id as id from thing where key='/type/list'"
    result = infobase_db.query(q1)
    try:
        kid = result[0].id 
    except IndexError:
        raise InvalidType("No id for type '/type/list' in the database")
    q2 = "select count(*) as count from thing where type=%d"%kid
    result = infobase_db.query(q2)
    total_lists = result[0].count
    # Computing total for covers (we find no. of editions with covers rather than total covers since this is more useful)
    total_covers = editions_db.view("admin/editions_with_covers", stale="ok").rows[0].value
    retval = dict(total_works    = works_db.info()["doc_count"],
                  total_editions = editions_db.info()["doc_count"],
                  total_covers   = total_covers,
                  total_authors  = total_authors,
                  total_subjects = total_subjects,
                  total_lists    = total_lists,
                  total_ebooks   = editions_db.view("admin/ebooks", stale="ok").rows[0].value)
    logging.debug("  %s", retval)
    return retval
    
def store_data(db, data, date):
    uid = "counts-%s"%date
    logging.debug("Updating admin_db for %s - %s", uid, data)
    try:
        vals = db[uid]
        vals.update(data)
    except couchdb.http.ResourceNotFound:
        vals = data
        db[uid] = vals
    db.save(vals)
    

def main(infobase_config, openlibrary_config, coverstore_config, ndays = 1):
    logging.basicConfig(level=logging.DEBUG, format = "[%(levelname)s] : %(filename)s:%(lineno)4d : %(message)s")
    logging.debug("Parsing config file")
    try:
        infobase_conn = connect_to_pg(infobase_config)
        coverstore_conn = connect_to_pg(coverstore_config)
        admin_db, editions_db, works_db, seeds_db = connect_to_couch(openlibrary_config)
    except KeyError,k:
        logging.critical("Config file section '%s' missing", k.args[0])
        return -1
    today = datetime.datetime.now() 
    yesterday = today - datetime.timedelta(days = 1)
    # Delta and total data is gathered only for the current day
    data = get_total_data(infobase_conn, editions_db, works_db, seeds_db)
    data.update(get_delta_data(admin_db, editions_db, seeds_db, today))
    store_data(admin_db, data, today.strftime("%Y-%m-%d"))
    logging.debug("Generating range data")
    for i in range(int(ndays)):
        yesterday = today - datetime.timedelta(days = 1)
        logging.debug(" From %s to %s", yesterday, today)
        data = get_range_data(infobase_conn, coverstore_conn, yesterday.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
        store_data(admin_db, data, yesterday.strftime("%Y-%m-%d"))
        today = yesterday
    return 0
