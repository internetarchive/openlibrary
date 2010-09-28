"""Postgres performance stats.
"""
import time
import web
import sys
import random

M = 1000000

def _timeit(db, n=1000):
    ids = [random.randint(1, 20*M) for i in range(n)]
    t0 = time.time()
    for id in ids:
        #db.query('SELECT * FROM data where thing_id=$id AND revision=1', vars=locals())
        db.query('SELECT * FROM thing WHERE key=$key', vars={'key': '/b/OL%dM' % id})
    t1 = time.time()
    return (t1-t0)/n

def timeit(f, repeat, *a):
    t0 = time.time()
    for i in range(repeat):
        f(*a)
    t1 = time.time()
    return (t1-t0)/repeat

def f(db, n):
    """Test with n random rows"""
    keys = ["/b/OL%dM" % random.randint(1, 20*1000000) for i in range(n)]
    db.query("SELECT * FROM thing WHERE key in $keys", vars=locals()).list()

def g(db, n):
    """Fetch n rows with consequtive keys"""
    start = random.randint(1, 20*1000000)
    keys = ["/b/OL%dM" % i  for i in range(start, start+n)]
    db.query("SELECT * FROM thing WHERE key in $keys", vars=locals()).list()

def main(host, dbname, n=1000):
    db = web.database(dbn='postgres', db=dbname, user='anand', pw='', host=host)
    db.printing = False
    print 'f', timeit(f, 10, db, 1000)
    print 'g', timeit(g, 10, db, 1000)

if __name__ == "__main__":
    if len(sys.argv) > 3:
        main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
    else:
        main(sys.argv[1], sys.argv[2])
