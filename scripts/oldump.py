#! /usr/bin/env python3

import sys

import _init_path


if __name__ == "__main__":
    print("{}: Python {}.{}.{}".format(__file__, *sys.version_info))

    from openlibrary.data import dump

    dump.main(sys.argv[1], sys.argv[2:])
