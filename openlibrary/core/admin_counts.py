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
    f = open(config_file)
    config = yaml.load(f)
    f.close()
    conf = {}
    conf["db"] = config["db_parameters"]["database"]
    host = config["db_parameters"].get("host")
    user = config["db_parameters"].get("username")
    if host:
        conf["host"] = host
    if user:
        conf["user"] = user
    logging.debug(" Postgres Database is %(db)s"%conf)
    return web.database(dbn="postgres",**conf)

def connect_to_couch(config_file):
    f = open(config_file)
    config = yaml.load(f)
    f.close()
    db = config["admin"]["counts_db"]
    logging.debug(" Couch Database is %s"%db)
    return couchdb.Database(db)

def get_data(db, start, end):
    """Returns the number of new records of type `typ` inserted between
    `start` and `end`"""
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

    retval = {}
    for typ in "work edition user author list".split():
        retval[typ] = _query_single_thing(db, typ, start, end)
        logging.debug(" Type : %s - %d"%(typ,retval[typ]))
    return retval


def store_data(db, data, date):
    uid = "counts-%s"%date
    try:
        vals = db[uid]
        vals.update(data)
    except couchdb.http.ResourceNotFound:
        vals = data
        db[uid] = vals
    db.save(vals)
    

def main(infobase_config, openlibrary_config, ndays = 1):
    logging.basicConfig(level=logging.DEBUG, format = "[%(levelname)s] : %(filename)s:%(lineno)d : %(message)s")
    logging.debug("Parsing config file")
    try:
        pg_conn = connect_to_pg(infobase_config)
        couch = connect_to_couch(openlibrary_config)
    except KeyError,k:
        logging.critical("Config file section '%s' missing"%k.args[0])
        return -1
    udate = datetime.datetime.now()
    for i in range(int(ndays)):
        ldate = udate - datetime.timedelta(days = 1)
        logging.debug("From %s to %s"%(ldate, udate))
        data = get_data(pg_conn, ldate.strftime("%Y-%m-%d"), udate.strftime("%Y-%m-%d"))
        store_data(couch, data, ldate.strftime("%Y-%m-%d"))
        udate = ldate
    return 0
