#! /usr/bin/env python
"""Script to update stats.
"""

import sys
import datetime

import _init_path
from openlibrary.api import OpenLibrary

def main(site, date=None):
    ol = OpenLibrary(site)
    ol.autologin("StatsBot")

    today = date or datetime.date.today().isoformat()
    print ol._request("/admin/stats/" + today, method='POST', data="").read()

if __name__ == "__main__":
    main(*sys.argv[1:])
    
