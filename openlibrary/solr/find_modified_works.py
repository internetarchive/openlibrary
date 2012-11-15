#!/usr/bin/env python

import argparse
import datetime
import itertools
import json
import os
import sys
import time
import urllib2

BASE_URL = "http://openlibrary.org/recentchanges/"
# BASE_URL = "http://0.0.0.0:8080/recentchanges/"

def parse_options(args):
    parser = argparse.ArgumentParser(description='Find works that have been changed in the given time period. With no options, goes into a loop and displays modified entries every 5 seconds.')
    parser.add_argument('-f', '--from', dest='frm', type=str, 
                        help='From date (yyyy/mm/dd)', default = False)
    parser.add_argument('-t', '--to', dest='to', type=str, 
                        help='To date (yyyy/mm/dd)', default = False)
    parser.add_argument('-s', '--start-time-file', dest='start_file', type=str, 
                        help='File to store last time looked at in loop mode', 
                        default = os.path.expanduser("~/.find_modified_works.date"))
    return parser.parse_args(args)

def extract_works(data):
    for i in data:
        for change in i['changes']:
            if change['key'].startswith("/works/"):
                yield change['key']

def get_modified_works(frm, to):
    one_day = datetime.timedelta(days = 1)
    ret = []
    logging.debug("Querying between %s and %s", frm, to)
    while frm < to:
        url = frm.strftime(BASE_URL+"%Y/%m/%d.json")
        logging.debug("Fetching changes from %s", url)
        ret.append(extract_works(json.load(urllib2.urlopen(url))))
        frm += one_day
    return itertools.chain(*ret)


def poll_for_changes(start_time_file):
    try:
        with open(start_time_file) as f:
            date = datetime.datetime.strptime(f.read(), "%Y/%m/%d")
            logging.debug("Obtained last end time from file")
    except IOError:
        date = datetime.datetime.now()
        logging.info("No state file. Starting from now.")
    current_day = date.day
    logging.debug("Starting at %s with current day %d", date, current_day)
    seen = set()
    while True:
        url = date.strftime(BASE_URL+"%Y/%m/%d.json")
        logging.debug("Fetching changes from %s", url)
        changes = list(json.load(urllib2.urlopen(url)))
        unseen_changes = list(x for x in changes if x['id'] not in seen)
        logging.debug("Total changes %d", len(changes))
        logging.debug("Unseen changes %d", len(unseen_changes))

        # Fetch works for all changesets we've not seen yet
        works = list(extract_works(unseen_changes))
        logging.debug("Number of works modified %d", len(works))

        # Record all the ones we've already emitted for this day
        for i in (x['id'] for x in unseen_changes):
            seen.add(i)

        # If the current day is over.
        if current_day != datetime.datetime.now().day:
            seen = set() # Clear things seen so far
            date = datetime.datetime.now() # Update date
            logging.debug("Flipping the clock to %s and clearing seen changes", date)

        for i in works:
            print i

        logging.debug("Number of Changes seen so far %d", len(list(seen)))
        logging.debug("Sleeping for 5")
        time.sleep(5)
        
        with open(start_time_file, "w") as f:
            logging.debug("Writing %s to state file", date.strftime("%Y/%m/%d"))
            f.write(date.strftime("%Y/%m/%d"))


    

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
        poll_for_changes(args.start_file)
    else:
        for i in get_modified_works(frm, to):
            print i
    


if __name__ == "__main__":
    import logging
    logging.basicConfig(level = logging.DEBUG, filename="/home/noufal/works.log")
    sys.exit(main())

