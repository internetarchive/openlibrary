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


def connect_to_admin(config_file):
    "Connects to the admin database in couchdb"
    f = open(config_file)
    config = yaml.load(f)
    f.close()
    db = config["admin"]["counts_db"]
    logging.debug(" Couch Database is %s"%db)
    return couchdb.Database(db)

def get_range_data(infobase_db, coverstore_db, start, end):
    """Returns the number of new records of various types
    between `start` and `end`"""
    def _query_single_thing(db, typ, start, end):
        "Query the counts a single type from the things table"
        q1 = "SELECT id as id from thing where key='/type/%s'"%typ
        result = db.query(q1)
        try:
            kid = result[0].id 
        except IndexError:
            raise InvalidType("No id for type '/type/%s in the datbase"%typ)
        q2 = "select count(*) as count from thing where type=%d and created >= '%s' and created < '%s'"%(kid, start, end)
        result = db.query(q2)
        count = result[0].count
        return count

    def _query_covers(db, start, end):
        "Queries the number of covers added between start and end"
        q1 = "SELECT count(*) as count from cover where created>= '%s' and created < '%s'"%(start, end)
        result = db.query(q1)
        count = result[0].count
        return count
        
        
    retval = {}
    for typ in "work edition user author list".split():
        retval[typ] = _query_single_thing(infobase_db, typ, start, end)
        logging.debug(" Type : %s - %d"%(typ,retval[typ]))
    retval["cover"] = _query_covers(coverstore_db, start, end)
    logging.debug(" Type : cover - %d"%retval[typ])
    return retval

def get_delta_data(db, start, end):
    """Returns the number of new records of `types` by calculating the
    difference between yesterdays numbers and todays"""

def store_data(db, data, date):
    uid = "counts-%s"%date
    try:
        vals = db[uid]
        vals.update(data)
    except couchdb.http.ResourceNotFound:
        vals = data
        db[uid] = vals
    db.save(vals)
    

def main(infobase_config, openlibrary_config, coverstore_config, ndays = 1):
    logging.basicConfig(level=logging.DEBUG, format = "[%(levelname)s] : %(filename)s:%(lineno)d : %(message)s")
    logging.debug("Parsing config file")
    try:
        infobase_conn = connect_to_pg(infobase_config)
        coverstore_conn = connect_to_pg(coverstore_config)
        couch = connect_to_admin(openlibrary_config)
    except KeyError,k:
        logging.critical("Config file section '%s' missing"%k.args[0])
        return -1
    udate = datetime.datetime.now()
    for i in range(int(ndays)):
        ldate = udate - datetime.timedelta(days = 1)
        logging.debug("From %s to %s"%(ldate, udate))
        data = get_range_data(infobase_conn, coverstore_conn, ldate.strftime("%Y-%m-%d"), udate.strftime("%Y-%m-%d"))
        store_data(couch, data, ldate.strftime("%Y-%m-%d"))
        udate = ldate
    return 0
