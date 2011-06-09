"""Script to add loan info to couchdb admin database from infobase logs.

USAGE: 

Pass all log entries as input to the script.

   $ cat logs/2011/05/*.log | python scripts/2011/05/load_loan_stats.py openlibrary.yml

Or only pass the store entries to run the script run faster.

   $ grep -h '"action": "store.' logs/2011/05/*.log | python scripts/2011/05/load_loan_stats.py openlibrary.yml
"""
import sys
import simplejson
import yaml
import couchdb
import logging
import re

logger = logging.getLogger('loans')

def get_couchdb_url(configfile):
    d = yaml.safe_load(open(configfile).read())
    return d['admin']['counts_db']
    
def read_log():
    for line in sys.stdin:
        line = line.strip()
        if line:
            try:
                yield simplejson.loads(line)
            except ValueError:
                logger.error("failed to parse log entry: %s", line, exc_info=True)

re_uuid = re.compile('^[0-9a-f]{32}$')
def is_uuid(s):
    return len(s) == 32 and re_uuid.match(s.lower())

def loan_start(db, row):    
    d = row['data']['data']
    key = "loans/" + row['data']['key']
    
    logger.info("log-start %s %s", key, row['timestamp'])  
    
    if key not in db:
        db[key] = {
            "_id": key,
            "book": d['book'],
            "resource_type": d['resource_type'],
            "t_start": row['timestamp'],
            "status": "active"
        }
    else:
        logger.warn("loan alredy present in the db: %s", key)

def loan_end(db, row):
    key = "loans/" + row['data']['key']

    logger.info("log-end %s %s", key, row['timestamp'])  
    
    loan = db.get(key)
    if loan:
        loan["status"] = "completed"
        loan["t_end"] = row['timestamp']
        
        db[key] = loan
    else:
        logger.warn("loan missing in the db: %s", key)

class CachedDB:
    def __init__(self, db):
        self.db = db
        self.cache = {}

    def commit(self):
        self.db.update(self.cache.values())
        self.cache.clear()
    
    def __contains__(self, key):
        return key in self.cache or key in self.db

    def get(self, key, default=None):
        if key in self.cache:
            return self.cache[key]
        else:
            return self.db.get(key, default)

    def __getitem__(self, key):
        if key in self.cache:
            return self.cache[key]
        else:
            return self.db[key]
    
    def __setitem__(self, key, doc):
        doc['_id'] = key
        self.cache[key] = doc
        if len(self.cache) > 100:
            self.commit()

def main(configfile):
    url = get_couchdb_url(configfile)
    db = couchdb.Database(url)
    db = CachedDB(db)
    
    for row in read_log():
        if row.get("action") == 'store.put' and row['data']['data'].get('type') == '/type/loan':
            loan_start(db, row)
        elif row.get("action") == 'store.delete' and is_uuid(row['data']['key']):
            loan_end(db, row)
    db.commit()
    
if __name__ == '__main__':
    FORMAT = "%(asctime)-15s %(levelname)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=FORMAT)
    
    main(sys.argv[1])
