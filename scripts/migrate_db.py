#! /usr/bin/env python
"""Script to migrate the OL database to latest schema.
"""

import itertools
import os
import sys

import simplejson
import web

changelog = """\
2010-04-22: 10 - Created unique index on thing.key
2010-07-01: 11 - Added `seq` table
2010-08-02: 12 - Added `data` column to transaction table.
2010-08-03: 13 - Added `changes` column to transaction table
2010-08-13: 14 - Added `transaction_index` table to index data in the transaction table.
"""

LATEST_VERSION = 14

class Upgrader:
    def upgrade(self, db):
        v = self.get_database_version(db)
        
        print "current db version:", v
        print "latest version:", LATEST_VERSION
        
        t = db.transaction()
        try:
            for i in range(v, LATEST_VERSION):
                print "upgrading to", i+1
                f = getattr(self, "upgrade_%03d" % (i+1))
                f(db)
        except: 
            print
            print "**ERROR**: Failed to complete the upgrade. rolling back..."
            print
            t.rollback()
            raise
        else:
            t.commit()
            print "done"
    
    def upgrade_011(self, db):
        """Add seq table."""
        q = """CREATE TABLE seq (
            id serial primary key,
            name text unique,
            value int default 0
        )"""
        db.query(q)
            
    def upgrade_012(self, db):
        """Add data column to transaction table."""
        db.query("ALTER TABLE transaction ADD COLUMN data text")
    
    def upgrade_013(self, db):
        """Add changes column to transaction table."""
        db.query("ALTER TABLE transaction ADD COLUMN changes text")
        
        # populate changes
        rows = db.query("SELECT thing.key, version.revision, version.transaction_id" 
            + " FROM  thing, version"
            + " WHERE thing.id=version.thing_id"
            + " ORDER BY version.transaction_id")
        
        for tx_id, changes in itertools.groupby(rows, lambda row: row.transaction_id):
            changes = [{"key": row.key, "revision": row.revision} for row in changes]
            db.update("transaction", where="id=$tx_id", changes=simplejson.dumps(changes), vars=locals())
        
    def upgrade_014(self, db):
        """Add transaction_index table."""
        
        q = """
        create table transaction_index (
            tx_id int references transaction,
            key text,
            value text
        );
        create index transaction_index_key_value_idx ON transaction_index(key, value);
        create index transaction_index_tx_id_idx ON transaction_index(tx_id);
        """
        db.query(q)

    def get_database_version(self, db):
        schema = self.read_schema(db)
    
        if 'seq' not in schema:
            return 10
        elif 'data' not in schema['transaction']:
            return 11
        elif 'changes' not in schema['transaction']:
            return 12
        elif 'transaction_index' not in schema:
            return 13
        else:
            return LATEST_VERSION

    def read_schema(self, db):
        rows = db.query("SELECT table_name, column_name,  data_type "
            + " FROM information_schema.columns"
            + " WHERE table_schema = 'public'") 

        schema = web.storage()
        for row in rows:
            t = schema.setdefault(row.table_name, web.storage())
            t[row.column_name] = row
        return schema

def usage():
    print >> sys.stderr
    print >> sys.stderr, "USAGE: %s dbname" % sys.argv[0]
    print >> sys.stderr

def main():
    if len(sys.argv) != 2:
        usage()
        sys.exit(1)
    elif sys.argv[1] in ["-h", "--help"]:
        usage()
    else:
        dbname = sys.argv[1]
        db = web.database(dbn='postgres', db=dbname, user=os.getenv('USER'), pw='')
        Upgrader().upgrade(db)
 
if __name__ == "__main__":
    main()
