#!/usr/bin/env python

# Simple script to check if a book is part of "Lending library" and currently available
# for loan
# 
# $ python scripts/2011/02/loan_status.py /books/OL6244901M && echo yes
# Not available
# 
# $ python scripts/2011/02/loan_status.py /books/OL6390314M && echo yes
# Available
# yes

import urllib2
import simplejson

host = 'http://openlibrary.org'
#host = 'http://mang-dev.us.archive.org:8080'

def get_loan_status(edition_key):
    global host
    status_url = '%s%s/loan_status/_borrow_status' % (host, edition_key)
    try:
        req = urllib2.Request(status_url)
        opener = urllib2.build_opener()
        f = opener.open(req)
        return simplejson.load(f)
    except:
        return None

def main():
    import sys
    if len(sys.argv) < 2:
        print "Usage: loan_status.py /books/OL123M"
        sys.exit(-1)
        
    status = get_loan_status(sys.argv[1])
    # print status
    if status is None:
        print 'Error retrieving status'
        sys.exit(1)
    elif status['loan_available'] and 'Lending library' in status['lending_subjects']:
        print 'Available'
        sys.exit(0)
    else:
        print 'Not available'
        sys.exit(2)

if __name__ == '__main__':
    main()
