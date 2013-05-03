"""Script find works that are not indexed in solr.

USAGE: zcat ol_dump_works_latest.txt.gz | cut -f2 | python scripts/2013/find-indexed-works.py http://solr-node:8983/solr/works
"""

import sys
import urllib
import json

solr_base_url = sys.argv[1]

def jsonget(url):
	print >> sys.stderr, "jsonget", url
	return json.load(urllib.urlopen(url))

def is_indexed_in_solr(key):
	url = solr_base_url + "/select?wt=json&rows=0&q=key:" + key
	d = jsonget(url)
	return d['response']['numFound'] > 0

def main():
	for line in sys.stdin:
		key = line.strip().split("/")[-1]
		if not is_indexed_in_solr(key):
			print line,

if __name__ == '__main__':
	main()