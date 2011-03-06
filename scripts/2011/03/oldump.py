"""Script to dump OL database from a given date and restore it to another db.

This script must be run on the db node.
"""
import os, sys
import web
import simplejson

db = None

engine = "postgres"
dbname = "openlibrary"
    
def read_transactions(txid):
    while True:
        rows = db.query("SELECT * FROM transaction where id > $txid order by id limit 100", vars=locals()).list()
        if not rows:
            return
            
        for row in rows:
            data = db.query("SELECT version.id as version_id, data.*"
                + " FROM version, data"
                + " WHERE version.thing_id=data.thing_id"
                + " AND version.revision=data.revision"
                + " AND version.transaction_id=$row.id",
                vars=locals())
            row._versions = data.list()
            row.created = row.created.isoformat()
            yield row
        txid = row.id
    
def dump(dirname, date):
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    dirname = os.path.abspath(dirname)
        
    txid = db.query("SELECT id FROM transaction where created >= $date order by id limit 1", vars=locals())[0].id
    txid = txid-1 # include txid also

    f_tx = open(os.path.join(dirname, "transactions.txt"), "w")
    f_docs = open(os.path.join(dirname, "docs.txt"), "w")
    for tx in read_transactions(txid):
        f_tx.write(simplejson.dumps(tx))
        f_tx.write("\n")
        for version in tx['_versions']:
            doc = simplejson.loads(version['data'])
            cols = [doc['key'], doc['type']['key'], doc['revision'], tx['id']]
            f_docs.write("\t".join(map(str, cols)) + "\n")
    f_tx.close()
            
    for t in ["account", "store", "store_index"]:
        filename = os.path.join(dirname, t + ".txt")
        db.query("COPY %s TO $filename" % t, vars=locals())
        
def has_transaction(txid):
    d = db.query("SELECT id FROM transaction WHERE id=$txid", vars=locals())
    return bool(d)

def update_seq(table):
    db.query("SELECT setval('%s_id_seq', (SELECT max(id) FROM %s))" % (table, table))
    
def get_thing_id(key):
    return db.query("SELECT id FROM thing WHERE key=$key", vars=locals())[0].id
        
def restore(dirname):
    dirname = os.path.abspath(dirname)
    tables = ["account", "store", "store_index"]
    
    tx = db.transaction()
    try:
        for line in open(os.path.join(dirname, "transactions.txt")):
            row = simplejson.loads(line)
            data = row.pop("_versions")
            if has_transaction(row['id']):
                print "ignoring tx", row['id']
                continue
        
            for d in data:
                id = d['thing_id']
                
                doc = simplejson.loads(d['data'])
                key = doc['key']
                type_id = get_thing_id(doc['type']['key'])
                
                if d['revision'] == 1:
                    db.insert("thing", seqname=False, 
                        id=d['thing_id'], key=key, type=type_id,
                        latest_revision=d['revision'],
                        created=row['created'], last_modified=row['created'])
                else:
                    db.update('thing', where="id=$id", 
                        type=type_id,
                        latest_revision=d['revision'],
                        last_modified=row['created'], 
                        vars=locals())
                        
            db.insert("transaction", seqname=False, **row)
    
            values = [{"id": d['version_id'], "thing_id": d['thing_id'], "revision": d['revision'], "transaction_id": row['id']} for d in data]
            db.multiple_insert("version", values, seqname=False)

            values = [{"data": d['data'], "thing_id": d['thing_id'], "revision": d['revision']} for d in data]
            db.multiple_insert("data", values, seqname=False)
                
        for table in ["thing", "version", "transaction", "store", "store_index"]:
            update_seq(table)
            
        for t in tables[::-1]:
            db.query("DELETE FROM %s" % t)

        for t in tables:
            filename = os.path.join(dirname, t + ".txt")
            db.query("COPY %s FROM $filename" % t, vars=locals())
    except:
        tx.rollback()
        raise
    else:
        tx.commit()
    
def main():
    global db
    db = web.database(dbn=engine, db=dbname, user=os.getenv("USER"), pw="")
    
    if "--restore" in sys.argv:
        db = web.database(dbn=engine, db="openlibrary2", user=os.getenv("USER"), pw="")
        restore(sys.argv[2])
    else:
        dump(sys.argv[1], sys.argv[2])
    
if __name__ == '__main__':
    main()    
