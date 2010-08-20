#! /usr/bin/env python
"""Script to generate <coverid, key, isbns> mapping for each active cover.
"""
import _init_path
from openlibrary.data.dump import read_tsv

import simplejson

def main(filename):
    for tokens in read_tsv(filename):
        json = tokens[-1]
        doc = simplejson.loads(json)
        
        cover = doc.get('covers') and doc.get('covers')[0]
        isbns = doc.get('isbn_10', []) + doc.get('isbn_13')
        key = doc['key']
        
        if cover and cover > 0:
            print "\t".join([cover, key, ",".join(isbns)])

if __name__ == '__main__':
    main(sys.argv[1])