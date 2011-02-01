#!/usr/bin/env python

import sys
sys.path.append("/opt/openlibrary/production/")
from openlibrary.admin import stats

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 5:
        print >>sys.stderr, "Usage : %s infobase_config openlibrary_config coverstore_config number_of_days"
        sys.exit(-1)
    sys.exit(stats.main(*sys.argv[1:]))
