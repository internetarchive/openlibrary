"""Load couchdb with OL data.
"""

import sys
import time
import couchdb

def group(items, size):
    """
        >>> list(group(range(7), 3))
        [[0, 1, 2], [3, 4, 5], [6]]
    """
    items = iter(items)
    while True:
        d = list(items.next() for i in xrange(size))
        if d:
            yield d
        else:
            break

def main(dbname, filename):
    server = couchdb.Server("http://localhost:5984/")
    db = server[dbname]
    
    t0 = time.time()
    for i, chunk in enumerate(group(open(filename), 1000)):
        if i%100 == 0:
            t1 = time.time()
            print i, "%.3f" % (t1-t0)
            t0 = t1

        json = '{"docs": [' + ",".join(chunk) +']}'
        print db.resource.post('_bulk_docs', content=json)

    print 'done'
    
if __name__ == '__main__':
    if len(sys.argv) == 1:
        import doctest
        doctest.testmod()
    else:
        main(sys.argv[1], sys.argv[2])
