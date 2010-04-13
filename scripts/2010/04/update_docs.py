#! /usr/bin/env python
"""Script to update documents in the Open Library database.

    USAGE: python update_docs.py database docs_file
    
The following example adds covers to edtions.
    
    $ cat docs.txt
    {"key": "/b/OL1M", "covers": [1, 2]}
    {"key": "/b/OL2M", "covers": [3, 4]}
    ...
    $ python update_docs.py openlibrary docs.txt
    
WARNING: This script doesn't update the index tables.
"""
import simplejson
import web
import os
import datetime

def read_docs(filename):
    """Read docs from the given file."""
    for line in open(filename):
        yield simplejson.loads(line.strip())    
        
def get_docs(db, keys):
    """Get the docs from DB."""
    rows = db.query("SELECT thing.id, thing.key, data.revision, data.data FROM thing, data WHERE thing.id = data.thing_id AND thing.latest_revision = data.revision AND key in $keys", vars=locals())
    rows = rows.list()
    for row in rows:
        row.doc = simplejson.loads(row.data)
        del row.data
    return rows
    
@web.memoize
def get_thing_id(db, key):
    return db.query("SELECT * FROM thing WHERE key=$key", vars=locals())[0].id

def update_docs(db, all_docs, chunk_size=10000, comment=""):
    now = datetime.datetime.utcnow()
    
    for chunk in web.group(all_docs, chunk_size):
        print chunk
        d = dict((doc['key'], doc) for doc in chunk)
        rows = get_docs(db, d.keys())
        
        for row in rows:
            row.doc.update(d[row.key])
            row.doc['revision'] = row.revision + 1
            row.doc['latest_revision'] = row.revision + 1
            row.doc['last_modified']['value'] = now.isoformat()
            
        data = [web.storage(thing_id=row.id, revision=row.revision+1, data=simplejson.dumps(row.doc)) for row in rows]
            
    author_id = get_thing_id(db, "/user/anand")
            
    t = db.transaction()
    try:
        tx_id = db.insert("transaction", author_id=author_id, action="bulk_update", ip="127.0.0.1", bot=True, created=now, comment=comment)
        db.multiple_insert("version", [dict(thing_id=d.thing_id, transaction_id=tx_id, revision=d.revision) for d in data], seqname=False)
        db.multiple_insert("data", data, seqname=False)
        db.query("UPDATE thing set latest_revision=latest_revision+1 WHERE key in $d.keys()", vars=locals())
    except:
        t.rollback()
        raise
    else:
        t.commit()

def main(dbname, docsfile, comment):
    db = web.database(dbn="postgres", db=dbname, user=os.getenv("USER"), pw="")
    docs = read_docs(docsfile)
    update_docs(db, docs, chunk_size=10000, comment=comment)
    
if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2], sys.argv[3])