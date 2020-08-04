#! /usr/bin/env python

from . import _init_path  # noqa: F401

from openlibrary.data import dump  # must be after _init_path

if __name__ == "__main__":
    import sys
    dump.main(sys.argv[1], sys.argv[2:])
