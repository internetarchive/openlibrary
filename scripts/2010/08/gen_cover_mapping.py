#! /usr/bin/env python
"""Script to generate <coverid, key, isbns> mapping for each active cover.
"""
import _init_path
from openlibrary.data.dump import read_tsv
import web

import simplejson
import sys

def main(filename):
    for tokens in read_tsv(filename):
        json = tokens[-1]
        doc = simplejson.loads(json)
        
        cover = doc.get('covers') and doc.get('covers')[0]
        isbns = doc.get('isbn_10', []) + doc.get('isbn_13', [])
        key = doc['key']

        key = web.safestr(key)
        isbns = (web.safestr(isbn) for isbn in isbns)
        
        try:
            if cover and cover > 0:
                print "\t".join([str(cover), key, ",".join(isbns)])
        except:
            print >> sys.stderr, doc
            print >> sys.stderr, (key, cover, isbns)
            raise

if __name__ == '__main__':
    main(sys.argv[1])
