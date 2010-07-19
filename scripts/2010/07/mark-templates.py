#! /usr/bin/env python
"""Script to mark the given templates as part of a plugin.

USAGE: python scripts/2010/07/mark-templates.py worksearch /upstream/templates/search/*
"""

import _init_path

import sys
from openlibrary.api import OpenLibrary

def main():
    ol = OpenLibrary()
    ol.autologin()

    plugin = sys.argv[1]

    all_docs = []

    for pattern in sys.argv[2:]:
        docs = ol.query({"key~": pattern, "*": None}, limit=1000)
        all_docs.extend(docs)

    for doc in all_docs:
        doc['plugin'] = plugin

    print ol.save_many(all_docs, comment="Marked as part of %s plugin." % plugin)

if __name__ == "__main__":
    main()
        
