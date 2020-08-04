#! /usr/bin/env python
import _init_path
from openlibrary.data import dump

if __name__ == "__main__":
    import sys
    dump.main(sys.argv[1], sys.argv[2:])
