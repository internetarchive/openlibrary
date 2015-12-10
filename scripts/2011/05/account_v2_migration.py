"""
Script to migrate accounts to new format.

Usage:
    $ python account_v2_migration.py infobase.yml
"""
from __future__ import with_statement
import _init_path

from infogami.infobase import server
from infogami.infobase._dbstore.store import Store

import sys
import yaml
import web

def migrate_account_table(db):
    def get_status(row):
        if row.get("verified"):
            return "active"
        else:
            return "pending"
            
    with db.transaction():
        store = Store(db)
    
        db.query("DECLARE longquery NO SCROLL CURSOR FOR SELECT thing.key, thing.created, account.* FROM thing, account WHERE thing.id=account.thing_id")
        while True:
            rows = db.query("FETCH FORWARD 100 FROM longquery").list()
            if not rows:
                break
                
            docs = []
            for row in rows:
                # Handle bad rows in the thing table.
                if not row.key.startswith("/people/"):
                    continue
                    
                username = row.key.split("/")[-1]
                doc = {
                    "_key": "account/" + username,
                    "type": "account",
            
                    "status": get_status(row),
                    "created_on": row.created.isoformat(),
            
                    "username": username,
                    "lusername": username.lower(),
            
                    "email": row.email,
                    "enc_password": row.password,
                    "bot": row.get("bot", False),
                }
                email_doc = {
                    "_key": "account-email/" + row.email,
                    "type": "account-email",
                    "username": username
                }
                docs.append(doc)
                docs.append(email_doc)
            store.put_many(docs)
        
def main(configfile):
    server.load_config(configfile)
    db = web.database(**web.config.db_parameters)

    with db.transaction():
        migrate_account_table(db)

if __name__ == '__main__':
    main(sys.argv[1])