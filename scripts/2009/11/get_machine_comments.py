"""Script to print key, machine_comment for all documents in OL.

USAGE: python get_machine_comments.py host dbname
"""
import web
import os
import sys

def main(host, db):
    user = os.getenv("USER")
    db = web.database(dbn="postgres", db="openlibrary", user=user, pw="", host=host)

    t = db.transaction()
    try:
        db.query("DECLARE datacur CURSOR FOR " + 
            " SELECT thing.key, version.machine_comment FROM thing, version" 
            " WHERE thing.id=version.thing_id AND version.machine_comment is not NULL"
            " ORDER BY thing.id")

        limit = 10000
        i = 0
        while True:
            i += 1
            result = db.query('FETCH FORWARD $limit FROM datacur', vars=locals())
            if not result:
                break
            sys.stdout.writelines("%s\t%s\n" % (row.key, row.machine_comment) for row in result)
    finally:
        t.rollback()

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

