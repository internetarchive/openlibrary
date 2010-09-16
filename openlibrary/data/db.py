#! /usr/bin/env python
"""Library to provide fast access to Open Library database.

How to use:
    
    from openlibrary.data import db
    
    db.setup_database(db='openlibrary', user='anand', pw='')
    db.setup_memcache(['host1:port1', 'host2:port2'])
    
    # get a set of docs
    docs = db.get_docs(['/sandbox'])
    
    # get all books
    books = dc.itedocs(type="/type/edition")
    
    # update docs
    db.update_docs(docs)
    
Each doc is a storage object with "id", "key", "revision" and "data".
"""

from openlibrary.utils import olmemcache
import simplejson
import web
import os
import datetime
import sys
import time

__all__ = [
    "setup_database", "setup_memcache",
    "longquery",
    "iterdocs",
    "get_docs", "update_docs"
]

db_parameters = None
db = None
mc = None

def setup_database(**db_params):
    """Setup the database. This must be called before using any other functions in this module.
    """
    global db, db_parameters
    db_params.setdefault('dbn', 'postgres')
    db = web.database(**db_params)
    db.printing = False
    db_parameters = db_params
    
def setup_memcache(servers):
    """Setup the memcached servers. 
    This must be called along with setup_database, if memcached servers are used in the system.
    """
    global mc
    mc = olmemcache.Client(["ia331532:7060", "ia331533:7060"])
    
def iterdocs(type=None):
    """Returns an iterator over all docs in the database.
    If type is specified, then only docs of that type will be returned.
    """
    q = 'SELECT id, key, latest_revision as revision FROM thing'
    if type:
        type_id = get_thing_id(type)
        q += ' WHERE type=$type_id'
    q += ' ORDER BY id'
        
    for chunk in longquery(q, locals()):
        docs = chunk
        _fill_data(docs)
        for doc in docs:
            yield doc
            
def longquery(query, vars, chunk_size=10000):
    """Execute an expensive query using db cursors.
    
    USAGE:
    
        for chunk in longquery("SELECT * FROM bigtable"):
            for row in chunk:
                print row
    """
    # DB cursor is valid only in the transaction
    # Create a new database to avoid this transaction interfere with the application code
    db = web.database(**db_parameters)
    db.printing = False
    
    tx = db.transaction()
    try:
        db.query("DECLARE longquery NO SCROLL CURSOR FOR " + query, vars=vars)
        while True:
            chunk = db.query("FETCH FORWARD $chunk_size FROM longquery", vars=locals()).list()
            if chunk:
                yield chunk
            else:
                break
    finally:
        tx.rollback()
        
def _fill_data(docs):
    """Add `data` to all docs by querying memcache/database.
    """
    def get(keys):
        if not keys:
            return []
        return db.query("SELECT thing.id, thing.key, data.revision, data.data"
            + " FROM thing, data"
            + " WHERE thing.id = data.thing_id"
            +   " AND thing.latest_revision = data.revision"
            +   " AND key in $keys", 
            vars=locals())
        
    keys = [doc.key for doc in docs]
    
    d = mc and mc.get_multi(keys) or {}
    debug("%s/%s found in memcache" % (len(d), len(keys)))

    keys = [doc.key for doc in docs if doc.key not in d]
    for row in get(keys):
        d[row.key] = row.data
    
    for doc in docs:
        doc.data = simplejson.loads(d[doc.key])
    return docs

def read_docs(keys, for_update=False):
    """Read the docs the docs from DB."""
    if not keys:
        return []
        
    debug("BEGIN SELECT")
    q = "SELECT thing.id, thing.key, thing.latest_revision as revision FROM thing WHERE key IN $keys"
    if for_update:
        q += " FOR UPDATE"
    docs = db.query(q, vars=locals())
    docs = docs.list()
    debug("END SELECT")
    _fill_data(docs)
    return docs
    
def update_docs(docs, comment, author, ip="127.0.0.1"):
    """Updates the given docs in the database by writing all the docs in a chunk. 
    
    This doesn't update the index tables. Avoid this function if you have any change that requires updating the index tables.
    """
    now = datetime.datetime.utcnow()
    author_id = get_thing_id(author)
    t = db.transaction()
    try:
        docdict = dict((doc.id, doc) for doc in docs)
        thing_ids = docdict.keys()

        # lock the rows in the table
        rows = db.query("SELECT id, key, latest_revision FROM thing where id IN $thing_ids FOR UPDATE", vars=locals())
        
        # update revision and last_modified in each document
        for row in rows:
            doc = docdict[row.id]
            doc.revision = row.latest_revision + 1
            doc.data['revision'] = doc.revision
            doc.data['latest_revision'] = doc.revision
            doc.data['last_modified']['value'] = now.isoformat()
        
        tx_id = db.insert("transaction", author_id=author_id, action="bulk_update", ip="127.0.0.1", created=now, comment=comment)
        debug("INSERT version")
        db.multiple_insert("version", [dict(thing_id=doc.id, transaction_id=tx_id, revision=doc.revision) for doc in docs], seqname=False)
        
        debug("INSERT data")
        data = [web.storage(thing_id=doc.id, revision=doc.revision, data=simplejson.dumps(doc.data)) for doc in docs]        
        db.multiple_insert("data", data, seqname=False)
        
        debug("UPDATE thing")
        db.query("UPDATE thing set latest_revision=latest_revision+1 WHERE id IN $thing_ids", vars=locals())
    except:
        t.rollback()
        debug("ROLLBACK")
        raise
    else:
        t.commit()
        debug("COMMIT")
        
        mapping = dict((doc.key, d.data) for doc, d in zip(docs, data))
        mc and mc.set_multi(mapping)
        debug("MC SET")

def debug(*a):
    print >> sys.stderr, time.asctime(), a
    
@web.memoize
def get_thing_id(key):
    return db.query("SELECT * FROM thing WHERE key=$key", vars=locals())[0].id

