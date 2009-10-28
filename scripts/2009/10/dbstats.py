"""Postgres performance stats.
"""
import time
import web
import sys
import random

M = 1000000

def timeit(db, n=1000):
    ids = [random.randint(1, 20*M) for i in range(n)]
    t0 = time.time()
    for id in ids:
        #db.query('SELECT * FROM data where thing_id=$id AND revision=1', vars=locals())
        db.query('SELECT * FROM thing WHERE key=$key', vars={'key': '/b/OL%dM' % id})
    t1 = time.time()
    return (t1-t0)/n

def main(host, dbname, n=1000):
    db = web.database(dbn='postgres', db=dbname, user='anand', pw='', host=host)
    db.printing = False
    print timeit(db, n)

if __name__ == "__main__":
    if len(sys.argv) > 3:
        main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
    else:
        main(sys.argv[1], sys.argv[2])
