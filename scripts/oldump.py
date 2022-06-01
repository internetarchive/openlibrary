#! /usr/bin/env python3

import sys
from datetime import datetime

import _init_path  # noqa: F401  Imported for its side effect of setting PYTHONPATH


if __name__ == "__main__":
    now = f"{datetime.now():%Y-%m-%d %H:%M:%S}"  # 2022-06-01 07:18:34
    py_ver = "Python {}.{}.{}".format(*sys.version_info)  # Python 3.10.4
    print(f"{now} [openlibrary.dump] {sys.argv} on {py_ver}", file=sys.stderr)

    from openlibrary.data import dump

    dump.main(sys.argv[1], sys.argv[2:])
