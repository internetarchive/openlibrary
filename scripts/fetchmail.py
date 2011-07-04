#!/usr/bin/env python

from openlibrary.core import fetchmail

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print "Usage : python fetchmail.py <openlibrary config file>"
        sys.exit(-2)
    sys.exit(fetchmail.main(*sys.argv[1:]))
