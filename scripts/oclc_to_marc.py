"""Find marc record URL from oclc number.

Usage: python oclc_to_marc.py oclc_1 oclc_2
"""
import requests

import urllib


root = "https://openlibrary.org"


def wget(path):
    return requests.get(root + path).json()


def find_marc_url(d):
    if d.get('source_records'):
        return d['source_records'][0]

    # some times initial revision is 2 instead of 1. So taking first 3 revisions (in reverse order)
    # and picking the machine comment from the last one
    result = wget('%s.json?m=history&offset=%d' % (d['key'], d['revision'] - 3))
    if result:
        return result[-1]['machine_comment'] or ""
    else:
        return ""


def main(oclc):
    query = urllib.parse.urlencode(
        {'type': '/type/edition', 'oclc_numbers': oclc, '*': ''}
    )
    result = wget('/query.json?' + query)

    for d in result:
        print("\t".join([oclc, d['key'], find_marc_url(d)]))


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 1 or "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__, file=sys.stderr)
    else:
        for oclc in sys.argv[1:]:
            main(oclc)
