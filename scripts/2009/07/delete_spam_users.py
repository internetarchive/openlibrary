"""
Earlier to block all the spam users, user's key has been prefixed with SPAM. That broke log-replay.

This script removes all the SPAM/* users to restore log-replay.
"""

import sys

def main(database):
    db = web.database(dbn='postgres', db=database, user=os.getenv('USER'), pw='')

    t = db.transaction()
    ids = [r.id for r in db.select('thing', where="key LIKE $pat", vars={'pat': 'SPAM%'})]
    
    db.update("transaction", author=None, where="author_id in $ids", vars=locals())
    db.update("version", author=None, where="author_id in $ids", vars=locals())

    for table in ['account', 'data', 'user_str', 'user_ref', 'user_int', 'user_boolean', 'user_float']:
        db.delete(table, where="thing_id in $ids", vars=locals())

    db.delete('thing', where='id in $ids', vars=locals())
    t.commit()

if __name__ == "__main__":
    main(sys.argv[1])
