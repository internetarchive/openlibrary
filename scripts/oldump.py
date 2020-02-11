#! /usr/bin/env python
from __future__ import absolute_import
from . import _init_path
from openlibrary.data import dump

if __name__ == "__main__":
    import sys
    dump.main(sys.argv[1], sys.argv[2:])
