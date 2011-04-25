"""Script to reindex specified transactions in the openlibrary database.

Some transcations/changesets in the openlibrary database have been not indexed
because of a bug. This script fixes the old records by reindexing the given
transactions.

USAGE: 

    $ python reindex_transactions.py transaction_id [transaction_id, ...]

It is possible to query the database to get the transaction ids and pass them to the script

    $ psql openlibrary -t  -c 'select id from transaction order by id desc limit 5' | xargs python reindex_transactions.py

"""

import logging
import sys
import os

import _init_path

import simplejson
import web
from infogami.infobase._dbstore.save import SaveImpl

logger = logging.getLogger("openlibrary.transactions")

@web.memoize
def get_db():
    # assumes that the name of the db is openlibrary
    return web.database(dbn="postgres", db="openlibrary", user=os.getenv("USER"), pw="")

def reindex_transaction(id):
    logging.info("reindexing %s", id)
    
    db = get_db()
    impl = SaveImpl(db)    
    
    with db.transaction():
        tx = db.query("SELECT id, data FROM transaction where id=$id", vars=locals())[0]
        db.delete("transaction_index", where="tx_id=$id", vars=locals())
        
        if tx.data:
            data = simplejson.loads(tx.data)
            impl._index_transaction_data(id, data)

def main():
    logger.info("BEGIN")
    for id in sys.argv[1:]:
        reindex_transaction(id)
    logger.info("END")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()