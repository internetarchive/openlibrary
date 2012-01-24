#!/usr/bin/env python

from openlibrary.core import fetchmail

if __name__ == "__main__":
    import sys
    sys.exit(fetchmail.main(sys.argv[1:]))
