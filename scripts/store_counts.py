#!/usr/bin/env python
"""
Script to read out data from thingdb and put it in couch so that it
can be queried by the /admin pages on openlibrary
"""

import logging
import datetime

import yaml
import couchdb
import psycopg2

class InvalidType(TypeError): pass

def connect_to_pg(config_file):
    with open(config_file) as f:
        config = yaml.load(f)
    db = config["db_parameters"]["database"]
    logging.debug(" Postgres Database is %s"%db)
    return psycopg2.connect("dbname = %s"%db)


def connect_to_couch(config_file):
    with open(config_file) as f:
        config = yaml.load(f)
    db = config["admin"]["counts_db"]
    logging.debug(" Couch Database is %s"%db)
    return couchdb.Database(db)

def get_data(db, typ, start, end):
    """Returns the number of new records of type `typ` inserted between
    `start` and `end`"""
    c = db.cursor()
    # logging.debug("   %s : %s to %s"%(typ, start, end))
    q1 = "SELECT id as id from thing where key='/type/%s'"%typ
    c.execute(q1)
    v = c.fetchone()
    if c:
        kid = int(v[0])
    else:
        raise InvalidType("No id for type '/type/%s in the datbase"%typ)
    q2 = "select count(*) as count from thing where type=%d and created >= '%s' and created < '%s'"%(kid, start, end)
    c.execute(q2)
    v = c.fetchall()
    count = v[0][0]
    # logging.debug("    %s"%count)
    return count

def store_data(db, typ, count, date):
    uid = "counts-%s"%date
    try:
        vals = db[uid]
    except couchdb.http.ResourceNotFound:
        vals = {}
        db[uid] = vals
    vals[typ] = count
    db.save(vals)
    


def main(infobase_config, openlibrary_config, ndays = 1):
    logging.basicConfig(level=logging.DEBUG, format = "[%(levelname)s] : %(filename)s:%(lineno)d : %(message)s")
    logging.debug("Parsing config file")
    pg_conn = connect_to_pg(infobase_config)
    couch = connect_to_couch(openlibrary_config)
    udate = datetime.datetime.now()
    for i in range(int(ndays)):
        ldate = udate - datetime.timedelta(days = 1)
        logging.debug("From %s to %s"%(ldate, udate))
        for typ in "work edition user author list".split():
            count = get_data(pg_conn, typ, ldate.strftime("%Y-%m-%d"), udate.strftime("%Y-%m-%d"))
            logging.debug(" Type : %s - %d"%(typ,count))
            store_data(couch, typ, count, ldate.strftime("%Y-%m-%d"))
        udate = ldate
    

    

if __name__ == "__main__":
    import sys
    sys.exit(main(*sys.argv[1:]))
