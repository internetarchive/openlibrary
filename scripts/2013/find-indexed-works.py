"""Script find works that are not indexed in solr.

USAGE: zcat ol_dump_works_latest.txt.gz | cut -f2 | python scripts/2013/find-indexed-works.py http://solr-node:8983/solr/works
"""

import sys
import urllib
import json
import time
import web

solr_base_url = sys.argv[1]

def jsonget(url, data=None):
	print >> sys.stderr, time.asctime(), "jsonget", url[:120], data[:50] if data else ""
	return json.load(urllib.urlopen(url, data))

def is_indexed_in_solr(key):
	url = solr_base_url + "/select?wt=json&rows=0&q=key:" + key
	d = jsonget(url)
	return d['response']['numFound'] > 0

def find_not_indexed(keys, chunk_size=1000):
	for chunk in web.group(keys, chunk_size):
		chunk = list(chunk)
		q=" OR ".join("key:" + k for k in chunk)
		params = urllib.urlencode({"q": q, "rows": chunk_size, "wt": "json", "fl": "key"})
		url = solr_base_url + "/select"
		d = jsonget(url, params)
		found = set(doc['key'] for doc in d['response']['docs'])
		for k in chunk:
			if k not in found:
				yield k

def main():
	keys = (line.strip().split("/")[-1] for line in sys.stdin)
	for k in find_not_indexed(keys):
		print k

if __name__ == '__main__':
	main()