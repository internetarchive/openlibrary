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
    parser = argparse.ArgumentParser(description="""Find works that have been changed in the given time period.

If the `from` or `to` options are specified. Prints works modified in that time period and quits.

Without these options, goes into loop mode which will keep polling openlibrary and print works modified on stdout. """)
    parser.add_argument('-f', '--from', dest='frm', type=str, 
                        help='From date (yyyy/mm/dd)', default = False)
    parser.add_argument('-t', '--to', dest='to', type=str, 
                        help='To date (yyyy/mm/dd)', default = False)
    parser.add_argument('-s', '--start-time-file', dest='start_file', type=str, 
                        help='File to store last time looked at in loop mode', 
                        default = os.path.expanduser("~/.find_modified_works.date"))
    parser.add_argument('-d', '--delay', dest='delay', type=int, default = 3,
                        help='Number of seconds to wait between polling openlibrary in loop mode')
    parser.add_argument('-m', '--max-chunk-size', dest='max_chunk_size', default = 100, type=int,
                        help='maximum number of works returned in each loop of the loop mode')
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


def poll_for_changes(start_time_file, max_chunk_size, delay):
    try:
        with open(start_time_file) as f:
            date = datetime.datetime.strptime(f.read(), "%Y/%m/%d")
            logging.debug("Obtained last end time from file '%s'"%start_time_file)
    except IOError:
        date = datetime.datetime.now()
        logging.info("No state file. Starting from now.")
    current_day = date.day
    logging.debug("Starting at %s with current day %d", date, current_day)
    logging.debug("Will emit at most %d works", max_chunk_size)
    seen = set()
    rest = []
    while True:
        url = date.strftime(BASE_URL+"%Y/%m/%d.json")
        logging.debug("-- Fetching changes from %s", url)
        changes = list(json.load(urllib2.urlopen(url)))
        unseen_changes = list(x for x in changes if x['id'] not in seen)
        logging.debug("%d changes fetched", len(changes))
        logging.debug(" of which %d are unseen", len(unseen_changes))

        # Fetch works for all changesets we've not seen yet. Add them
        # to the ones left over from the previous iteration.
        works = list(extract_works(unseen_changes)) 
        logging.debug("  in which %d have works modified.", len(works))
        logging.debug("  There are %d left over works from the last iteration.", len(rest))
        works += rest
        logging.debug("    Totally %d works to be emitted"%len(works))

        # Record all the ones we've already emitted for this day
        for i in (x['id'] for x in unseen_changes):
            seen.add(i)

        logging.debug("Number of Changes seen so far %d", len(list(seen)))
        # If the current day is over.
        if current_day != datetime.datetime.now().day:
            seen = set() # Clear things seen so far
            date = datetime.datetime.now() # Update date
            current_day = date.day
            logging.debug("Flipping the clock to %s and clearing seen changes", date)

        # If there are too many works, emit only max_chunk_size
        # works. Keep the rest for the next iteration
        if len(works) > max_chunk_size:
            logging.debug("  Number of works to be emitted (%d) is more than %s", len(works), max_chunk_size)
            to_be_emitted, rest = works[:max_chunk_size], works[max_chunk_size:]
            logging.debug("    Retaining %s", len(rest))
        else:
            to_be_emitted, rest = works, []
            

            
        if to_be_emitted:
            logging.debug("Emitting %d works", len(to_be_emitted))
            for i in to_be_emitted:
                print i

        logging.debug("Sleeping for %d seconds", delay)
        time.sleep(delay)
        
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
        poll_for_changes(args.start_file, args.max_chunk_size, args.delay)
    else:
        for i in get_modified_works(frm, to):
            print i
    


if __name__ == "__main__":
    import logging
    logging.basicConfig(level = logging.DEBUG, format="%(levelname)-7s (%(asctime)s) : %(message)s")#, filename="/home/noufal/works.log")
    sys.exit(main())

