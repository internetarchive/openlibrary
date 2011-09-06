"""Script to match Smithsonian artist names with OL.
"""

import web
import csv
import urllib
import simplejson
import logging
import sys

logger = logging.getLogger()

base_url = "http://openlibrary.org/search/authors.json"
base_url = "http://anand.openlibrary.org/search/authors.json"

def query_authors(lastname, firstname, birth_date):
    if not birth_date:
        return
    url = base_url + "?" + urllib.urlencode({"q": "%s %s birth_date:%s" % (lastname, firstname, birth_date)}) 
    json = urllib.urlopen(url).read()
    data = simplejson.loads(json)
    n = data['numFound']
    logger.info("query for %s. found %d matches", (lastname, firstname, birth_date), n)
    if n == 1:
        return '/authors/' + data['docs'][0]['key']
    
def read(filename):
    rows = csv.reader(open(filename))
    cols = [c.strip() for c in rows.next()]
    logging.info("reading cols %s", cols)

    for row in rows:
        row = [val.strip() for val in row]
        yield web.storage(zip(cols, row))

def match(record):
    key = query_authors(record['aaa_last'], record['aaa_first'], record['aaa_date_born'])
    if key:
        record.openlibrary = "http://openlibrary.org" + key
    else:
        record.openlibrary = ""

def main(filename):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    records = read(filename)

    cols =["aaa_last", "aaa_first", "aaa_date_born", "aaa_date_died", "fullurl", "openlibrary"]
    for r in records:
        match(r)
        print "\t".join(r[c] for c in cols)

if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except:
        sys.stdout.flush()
        raise
