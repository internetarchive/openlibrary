"""script to compare performance of simplejson and jsonlib.
"""

import sys, time, urllib2
import simplejson
import jsonlib, jsonlib2, yajl

def read():
    for  line in open(sys.argv[1]):
        yield line.strip().split("\t")[-1]


def timeit(label, seq):
    t0 = time.time()
    for x in seq:
        pass
    t1 = time.time()
    print label, "%.2f sec" % (t1-t0)

if False and __name__ == "__main__":
    timeit("read", read())
    timeit("simplejson.load", (simplejson.loads(json) for json in read()))
    timeit("jsonlib.load", (jsonlib.loads(json) for json in read()))
    
    
    timeit("simplejson.load-dump", (simplejson.dumps(simplejson.loads(json)) for json in read()))
    timeit("jsonlib.load-dump", (jsonlib.dumps(jsonlib.loads(json)) for json in read()))


def bench(count, f, *args):
    times = []
    for _ in range(count):
        t0 = time.time()
        f(*args)
        times.append(time.time() - t0)
    times = sorted(times)
    return "avg %.5f med %.5f max %.5f min %.5f" % (
        sum(times) / float(len(times)),
        times[int(len(times) / 2.0)],
        times[-1],
        times[0]
   )

if True and __name__ == "__main__":
    for b in (
        simplejson.dumps({"str": "value", 
                          "num": 1.0, 
                          "strlist": ["a", "b", "c"],
                          "numlist": range(1000)}),
        urllib2.urlopen("http://freebase.com/api/trans/notable_types_2?id=/en/bob_dylan").read(),
        urllib2.urlopen("http://freebase.com/api/trans/popular_topics_by_type_debug?id=/film/actor").read()
    ):
        print "-" * 80
        print "%s char blob" % len(b)
        print "-" * 80
        impls = (simplejson, jsonlib, jsonlib2, yajl)
        print "loads"
        for impl in impls:
            print "%s: %s" % (impl.__name__.ljust(10), bench(100, impl.loads, b))
        print "dumps"
        for impl in impls:
            print "%s: %s" % (impl.__name__.ljust(10), bench(100, impl.dumps, impl.loads(b)))
