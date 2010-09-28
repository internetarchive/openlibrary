import _init_path
from openlibrary.utils import olmemcache
import web
import time

def main():
    m = olmemcache.Client(["ia331532:7060", "ia331533:7060"])
    db = web.database(dbn="postgres", db="openlibrary", user="anand", pw="", host="ia331526")

    t = db.transaction()
    try:
        db.query("DECLARE datacur CURSOR FOR SELECT thing.key, data.data FROM thing, data WHERE thing.id=data.thing_id and data.revision=thing.latest_revision ORDER BY thing.id")
        limit = 10000
        i = 0
        while True:
            i += 1
            result = db.query('FETCH FORWARD $limit FROM datacur', vars=locals()).list()
            if not result:
                break
            t1 = time.time()
            d = dict((r.key, r.data) for r in result)
            try:
                m.set_multi(d)
                #m.add_multi(d)
            except:
                m.delete_multi(d.keys())
                print >> web.debug, 'failed to add to memcached', repr(r.key)

            t2 = time.time()
            print >> web.debug, "%.3f" % (t2-t1), i, "adding memcache records"
    finally:
        t.rollback()

if __name__ == "__main__":
    main()
