#!/usr/bin/python

from __future__ import print_function
from time import sleep, time
import web
import subprocess
import sys
from catalog.read_rc import read_rc

from six.moves import urllib


rc = read_rc()

def solr_query(q, start=0, rows=None, sort_by="publicdate desc"):
    q += " AND NOT collection:test_collection AND NOT collection:opensource AND NOT collection:microfilm"
#    q += " AND NOT collection:test_collection AND collection:gutenberg"
    url = rc['solr_url'] + "?q=%s;%s&wt=json&start=%d" % (urllib.parse.quote(q), urllib.parse.quote_plus(sort_by), start)
    if rows:
        url += "&rows=%d" % rows
    ret = eval(urllib.request.urlopen(url).read())
    return ret['response']

def get_books(**args):
    ret = solr_query("mediatype:texts AND format:scandata", **args)
    #ret = solr_query("mediatype:texts", **args)
    return [d['identifier'] for d in ret['docs']]

if __name__ == '__main__':
    rows = 1000
    out = open(sys.argv[1], 'w')
    for i in range(20):
        print(i)
        books = list(get_books(rows=rows, start=i * rows))
        if not books:
            break
        for b in books:
            print(b, file=out)
    out.close()

    print("finished")
