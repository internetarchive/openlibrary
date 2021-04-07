"""Create changes dump of OL.

USAGE: python chanages_dump.py dbname
"""
import web
import os
import simplejson

def fetch(db, query, size=10000):
    t = db.transaction()
    try:
        db.query("DECLARE _fetch NO SCROLL CURSOR FOR " + query)
        while True:
            rows = db.query("FETCH FORWARD $size FROM _fetch", vars=locals())
            if rows:
                for row in rows:
                    yield row
            else:
                break
    finally:
        t.rollback()

def load_authors(db):
    d = {}
    for row in fetch(db, "SELECT thing.id, thing.key FROM thing, account WHERE account.thing_id=thing.id"):
        d[row.id] = row.key
    return d

def main(dbname):
    db = web.database(dbn="postgres", db=dbname, user=os.getenv("USER"), pw="")
    authors = load_authors(db)

    q = ( "SELECT t.*, thing.key, version.revision"
        + " FROM transaction t, thing, version"
        + " WHERE version.transaction_id=t.id AND version.thing_id=thing.id"
        + " ORDER BY t.created"
        )

    for row in fetch(db, q, 10000):
        row.author = {"key": row.author_id and authors.get(row.author_id)}
        del row.author_id
        row.comment = row.comment or ""
        row.ip = row.ip or ""
        row.created = row.created.isoformat()
        print simplejson.dumps(row) + "\t" + row.created

if __name__ == "__main__":
    import sys
    main(sys.argv[1])
