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

def get_db_creds(config_file):
    with open(config_file) as f:
        config = yaml.load(f)
    db = config["db_parameters"]["database"]
    logging.debug(" Database is %s"%db)
    return db

def get_data_count(db, typ, start, end):
    """Returns the number of new records of type `typ` inserted between
    `start` and `end`"""
    c = db.cursor()
    logging.debug("   %s : %s to %s"%(typ, start, end))
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
    logging.debug("    %s"%count)
    return count


def main(config_file, ndays = 1):
    logging.basicConfig(level=logging.DEBUG, format = "[%(levelname)s] : %(filename)s:%(lineno)d : %(message)s")
    logging.debug("Parsing config file")
    db = get_db_creds(config_file)
    logging.debug("Connecting to database")
    pg_conn = psycopg2.connect("dbname = %s"%db)
    couch_conn = 
    cday = datetime.datetime.now()
    for i in range(int(ndays)):
        lday = cday - datetime.timedelta(days = 1)
        logging.debug("From %s to %s"%(lday,cday))
        for typ in "work edition user author list".split():
            logging.debug(" Type : %s"%typ)
            c = get_data_count(pg_conn, typ, lday.strftime("%Y-%m-%d"), cday.strftime("%Y-%m-%d"))
            store_data(couch_conn, c)

        cday = lday
    

    

if __name__ == "__main__":
    import sys
    sys.exit(main(*sys.argv[1:]))
