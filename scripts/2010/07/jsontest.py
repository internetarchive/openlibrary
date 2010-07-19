"""script to compare performance of simplejson and jsonlib.
"""

import sys, time
import simplejson
import jsonlib

def read():
    for  line in open(sys.argv[1]):
        yield line.strip().split("\t")[-1]


def timeit(label, seq):
    t0 = time.time()
    for x in seq:
        pass
    t1 = time.time()
    print label, "%.2f sec" % (t1-t0)


timeit("read", read())
timeit("simplejson.load", (simplejson.loads(json) for json in read()))
timeit("jsonlib.load", (jsonlib.loads(json) for json in read()))


timeit("simplejson.load-dump", (simplejson.dumps(simplejson.loads(json)) for json in read()))
timeit("jsonlib.load-dump", (jsonlib.dumps(jsonlib.loads(json)) for json in read()))

