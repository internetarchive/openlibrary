#!/usr/bin/env python

import argparse
import datetime
import itertools
import json
import os
import pprint
import sys
import urllib2

BASE_URL = "http://openlibrary.org/recentchanges/"
BASE_URL = "http://0.0.0.0:8080/recentchanges/"

def parse_options(args):
    parser = argparse.ArgumentParser(description='Find works that have been changed in the given time period. With no options, goes into a loop and displays modified entries every 5 seconds.')
    parser.add_argument('-f', '--from', dest='frm', type=str, 
                        help='From date (yyyy/mm/dd)', default = False)
    parser.add_argument('-t', '--to', dest='to', type=str, 
                        help='To date (yyyy/mm/dd)', default = False)
    parser.add_argument('-s', '--start_file', dest='start_file', type=str, 
                        help='File to store last time looked at in loop mode', 
                        default = os.path.expanduser("~/.find_modified_works.date"))
    return parser.parse_args(args)

def extract_works(data):
    data = json.loads(data)
    for i in data:
        for change in i['changes']:
            if change['key'].startswith("/works/"):
                yield change['key']

def get_modified_works(frm, to):
    one_day = datetime.timedelta(days = 1)
    ret = []
    while frm < to:
        url = frm.strftime(BASE_URL+"%Y/%m/%d.json")
        ret.append(extract_works(urllib2.urlopen(url).read()))
        frm += one_day
    return itertools.chain(*ret)


def poll_for_changes(frm = False):
    pass

def main():
    args = parse_options(sys.argv[1:])
    loop = not args.frm and not args.to
    if args.frm:
        frm = datetime.datetime.strptime(args.frm, "%Y/%m/%d")
    else:
        frm = datetime.datetime.now() - datetime.timedelta(days = 1)

    if args.to:
        frm = datetime.datetime.strptime(frm, "%Y/%m/%d")
    else:
        to = datetime.datetime.now()
        
    if loop:
        poll_for_changes(frm)

    for i in get_modified_works(frm, to):
        print i
    


if __name__ == "__main__":
    sys.exit(main())

