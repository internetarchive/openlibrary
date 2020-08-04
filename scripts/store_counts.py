#!/olsystem/bin/olenv python

from __future__ import print_function
import sys

from . import _init_path  # noqa: F401

from openlibrary.admin import stats  # must be after _init_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 5:
        print("Usage : %s infobase_config openlibrary_config coverstore_config number_of_days", file=sys.stderr)
        sys.exit(-1)
    sys.exit(stats.main(*sys.argv[1:]))
