#!/usr/bin/env python

import sys
sys.path.append("/opt/openlibrary/production/")
from openlibrary.core import admin_counts

if __name__ == "__main__":
    import sys
    sys.exit(admin_counts.main(*sys.argv[1:]))
