#! /usr/bin/env python
"""Script to inspect memcache.

Usage:
    python scripts/2011/08/inspect-memcache.py localhost:7060
"""

import sys
import memcache

mc = memcache.Client([sys.argv[1]])

slabs = mc.get_stats("slabs")[0][1]
keys = sorted([key.split(":")[0] for key in slabs if "chunk_size" in key], key=lambda k: int(k))
for k in keys:
    print k
    print "  chunk_size", slabs[k + ":chunk_size"]
    print "  total_chunks", slabs[k + ":total_chunks"]
    dump = mc.get_stats("cachedump %s 5" % k)[0][1]
    for dk, dv in dump.items():
        print "  " + dk, dv
