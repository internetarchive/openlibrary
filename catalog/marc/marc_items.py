import sys
from MARC21 import *
from MARC21Biblio import *

#-- configuration
input_file = sys.stdin
only = False    # set to a number N to parse only the first N records

def process_item (item):
    print item

def parse_file (file):
    f = MARC21BiblioFile (file)
    n = 0
    p = 0
    try:
        while True:
            if only and n == only:
                break
            try:
                item = f.next()
                process_item (item)
                p += 1
            except MARC21Exn, e:
                sys.stderr.write ("couldn't interpret item %d: %s\n" % (n, e))
            n += 1
            if n % 1000 == 0:
                sys.stderr.write ("read %d records\n" % n)
    except StopIteration:
        pass
    sys.stderr.write ("read %d records\n" % n)
    sys.stderr.write ("interpreted %d records\n" % p)

parse_file (input_file)
