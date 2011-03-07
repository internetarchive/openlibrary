"""Script to dump OL database from a given date and restore it to another db.

This script must be run on the db node.
"""
import os, sys
import web
import simplejson
from infogami.infobase._dbstore.save import IndexUtil
from openlibrary.core import schema

db = None

engine = "postgres"
dbname = "openlibrary"
        
class RestoreEngine:
    """Engine to update an existing database with new changes from a dump.
    """
    def __init__(self, dirname):
        self.dirname = dirname
        self.index_engine = IndexUtil(db, schema.get_schema())
        
    def path(self, filename):
        return os.path.abspath(os.path.join(self.dirname, filename))
        
    def restore(self):
        self.restore_transactions()
        self.restore_tables()
        self.restore_sequences()
        
    def restore_sequences(self):
        d = simplejson.loads(open(self.path("sequences.txt")).read())
        
        for name, value in d.items():
            db.query("SELECT setval($name, $value)", vars=locals())
        
    def restore_tables(self):
        # some tables can't be restored before some other table is restored because of foreign-key constraints.
        # This dict specified the order. Smaller number must be restored first.
        order = {
            "store": 1,
            "store_index": 2
        }
        
        tables = [f[len("table_"):-len(".txt")] for f in os.listdir(self.dirname) if f.startswith("table_")]
        tables.sort(key=lambda key: order.get(key, 0))
        
        for t in tables[::-1]:
            db.query("DELETE FROM %s" % t)

        for t in tables:
            filename = self.path("table_%s.txt" % t)
            db.query("COPY %s FROM $filename" % t, vars=locals())
            
    def get_doc(self, thing_id, revision):
        d = db.query("SELECT data FROM data WHERE thing_id=$thing_id AND revision=$revision", vars=locals())
        try:
            return simplejson.loads(d[0].data)
        except IndexError:
            return {}
            
    def restore_tx(self, row):
        data = row.pop("_versions")

        tx = db.transaction()
        try:
            old_docs = []
            new_docs = []
            for d in data:
                id = d['thing_id']

                doc = simplejson.loads(d['data'])
                key = doc['key']
                type_id = self.get_thing_id(doc['type']['key'])

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
                    old_docs.append(self.get_doc(d['thing_id'], d['revision']-1))
                new_docs.append(doc)

            db.insert("transaction", seqname=False, **row)

            values = [{"id": d['version_id'], "thing_id": d['thing_id'], "revision": d['revision'], "transaction_id": row['id']} for d in data]
            db.multiple_insert("version", values, seqname=False)

            values = [{"data": d['data'], "thing_id": d['thing_id'], "revision": d['revision']} for d in data]
            db.multiple_insert("data", values, seqname=False)
            
            self.delete_index(old_docs)
            self.insert_index(new_docs)
        except:
            tx.rollback()
            raise
        else:
            tx.commit()
        
    def restore_transactions(self):
        for line in open(self.path("transactions.txt")):
            row = simplejson.loads(line)
            if self.has_transaction(row['id']):
                print "ignoring tx", row['id']
                continue
            else:
                self.restore_tx(row)
                
    def has_transaction(self, txid):
        d = db.query("SELECT id FROM transaction WHERE id=$txid", vars=locals())
        return bool(d)

    def get_thing_id(self, key):
        return db.query("SELECT id FROM thing WHERE key=$key", vars=locals())[0].id
        
    def _process_key(self, key):
        # some data in the database still has /b/ instead /books. 
        # The transaformation is still done in software.
        mapping = (
            "/l/", "/languages/",
            "/a/", "/authors/",
            "/b/", "/books/",
            "/user/", "/people/"
        )

        if "/" in key and key.split("/")[1] in ['a', 'b', 'l', 'user']:
            for old, new in web.group(mapping, 2):
                if key.startswith(old):
                    return new + key[len(old):]
        return key
            
    def delete_index(self, docs):
        all_deletes = {}
        for doc in docs:
            doc = dict(doc, _force_reindex=True)
            dummy_doc = {"key": self._process_key(doc['key']), "type": {"key": "/type/foo"}}
            deletes, _inserts = self.index_engine.diff_index(doc, dummy_doc)
            all_deletes.update(deletes)
            
        all_deletes = self.index_engine.compile_index(all_deletes)
        self.index_engine.delete_index(all_deletes)
        
    def insert_index(self, docs):
        all_inserts = {}
        for doc in docs:
            _deletes, inserts = self.index_engine.diff_index({}, doc)
            all_inserts.update(inserts)
            
        all_inserts = self.index_engine.compile_index(all_inserts)
        self.index_engine.insert_index(all_inserts)
    
    
class DumpEngine:
    def __init__(self, dirname):
        self.dirname = dirname
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        
        # make sure postgres can write to the dir. Required to copy tables.
        os.system("chmod 777 " + dirname)
        
    def path(self, filename):
        return os.path.abspath(os.path.join(self.dirname, filename))
        
    def dump(self, date):
        self.dump_transactions(date)
        self.dump_tables()
        self.dump_sequences()
        
    def dump_transactions(self, date):
        txid = db.query("SELECT id FROM transaction where created >= $date order by id limit 1", vars=locals())[0].id
        txid = txid-1 # include txid also

        f = open(self.path("transactions.txt"), "w")
        for tx in self.read_transactions(txid):
            row = simplejson.dumps(tx) + "\n"
            f.write(row)
        f.close()
            
    def dump_tables(self):
        for t in ["account", "store", "store_index", "seq"]:
            filename = self.path("table_%s.txt" % t)
            db.query("COPY %s TO $filename" % t, vars=locals())
            
    def dump_sequences(self):
        sequences = db.query("SELECT c.relname as name FROM pg_class c WHERE c.relkind = 'S'")
        d = {}
        for seq in sequences:
            d[seq.name] = db.query("SELECT last_value from %s" % seq.name)[0].last_value

        f = open(self.path("sequences.txt"), "w")
        f.write(simplejson.dumps(d) + "\n")
        f.close()
    
    def read_transactions(self, txid):
        """Returns an iterator over transactions in the db starting from the given transaction ID.
        """
        while True:
            rows = db.query("SELECT * FROM transaction where id >= $txid order by id limit 100", vars=locals()).list()
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
            txid = row.id+1
        
def main():
    global db
    db = web.database(dbn=engine, db=dbname, user=os.getenv("USER"), pw="")
    
    if "--restore" in sys.argv:
        sys.argv.remove("--restore")
        e = RestoreEngine(sys.argv[1])
        e.restore()
    else:
        dirname = sys.argv[1]
        date = sys.argv[2]
        e = DumpEngine(dirname)
        e.dump(date)
    
if __name__ == '__main__':
    main()    
