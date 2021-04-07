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

        logging.info("tx.data %s", tx.data)
        if tx.data:
            data = simplejson.loads(tx.data)
            impl._index_transaction_data(id, data)

def verify_index(tx_id):
    logging.info("verifying %s", tx_id)
    db = get_db()
    impl = SaveImpl(db)
    tx = db.query("SELECT id, action, created, data FROM transaction where id=$tx_id", vars=locals())[0]

    if tx.data:
        d = db.query("SELECT * FROM transaction_index WHERE tx_id=$tx_id", vars=locals())
        index = sorted((row.key, row.value) for row in d)

        tx_data = simplejson.loads(tx.data)
        index2 = compute_index(tx_data)
        if index != index2:
            print "\t".join([str(x) for x in [tx.id, tx.action, tx.created.isoformat(), index, index2]])

def compute_index(tx_data):
    d = []
    def index(key, value):
        if isinstance(value, (basestring, int)):
            d.append((key, value))
        elif isinstance(value, list):
            for v in value:
                index(key, v)

    for k, v in tx_data.iteritems():
        index(k, v)
    return sorted(d)

def main():
    logger.info("BEGIN")
    for id in sys.argv[1:]:
        reindex_transaction(id)
    logger.info("END")

def main_verify():
    logger.info("BEGIN")
    for id in sys.argv[1:]:
        verify_index(id)
    logger.info("END")

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

    if "--verify" in sys.argv:
        sys.argv.remove("--verify")
        main_verify()
    else:
        main()