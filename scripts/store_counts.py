#!/usr/bin/env python

import sys

import _init_path  # noqa: F401  Imported for its side effect of setting PYTHONPATH

from openlibrary.admin import stats

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 5:
        print(
            "Usage : %s infobase_config openlibrary_config coverstore_config number_of_days",
            file=sys.stderr,
        )
        sys.exit(-1)
    sys.exit(stats.main(*sys.argv[1:]))
