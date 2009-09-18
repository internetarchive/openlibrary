"""Because edition object doesn't have scan_records property, an
infobase query is made to check whether there exists a scan_record for
that edition. This is done for rendering each and every edition
page. This query can be eliminated of scan_records are linked to the
edition pages. By doing so, only the editions which has scan_records
will make additional query.

This script finds all scan_record objects in the system and links them to corresponding edition object.

USAGE:

    python link_scan_records.py http://dev.openlibrary.org
"""

import _init_path
from openlibrary.api import OpenLibrary

def take(n, items):
    def f(items):
        for i in range(n):
            yield items.next()
    return list(f(iter(items)))

def main(server):
    ol = OpenLibrary(server)
    ol.autologin()

    scan_records = ol.query(type='/type/scan_record', limit=False, edition={'*': None})
    editions = (r['edition'] for r in scan_records)

    # process 1000 editions at a time.
    while True:
        chunk = take(1000, editions)
        if not chunk:
            break

        print 'linking %d editions' % len(chunk)
        
        for e in chunk:
            e['scan_records'] = [{'key': '/scan_record' + e['key']}]
            
        ol.save_many(chunk, 'link scan records')

if __name__ == "__main__":
    import sys
    main(sys.argv[1])
