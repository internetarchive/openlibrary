#! /usr/bin/env python
"""Generates a JSON dump suitable for solr import from openlibrary dumps.

Glossary:

xwork document:

	A dictionary contains all informatation about a work. It contains the following fields.

	work - The work document
	editions - The list of edition documents belong to the work
	authors - The list of authors of this work
	ia - dictionary of ia metadata of all ia-ids referenced in the editions
	duplicates - dict of duplicates mapping for key to all it's duplicates

solr document:

	A dictionary with elements from Solr schema of Open Library. These 
	documents can be imported to solr after converting to xml.
"""
import sys
import json
import gzip
import web

from update_work import process_edition_data, process_work_data

def process_xwork(doc):
	"""Process xwork document and yield multiple solr documents.
	"""
	work = doc['work']
	editions = doc['editions']
	authors = doc['authors']
	ia = doc['ia']

	d = dict(work=work, editions=editions, authors=authors, ia=ia, duplicates={})
	yield process_work_data(d)

	for e in editions:
		d = web.storage(edition=e, work=work, authors=authors)
		yield process_edition_data(d)

def xopen(path, mode="r"):
	if path.endswith(".gz"):
		return gzip.open(path, mode)
	else:
		return open(path, mode)

def read_xworks_dump(filename):
	for line in xopen(filename):
		key, jsontext = line.strip().split("\t")
		yield json.loads(jsontext)

def write_solr_dump(docs):
	for doc in docs:
		print json.dumps(doc)

def main(xworks_filename):
	solr_docs = (doc for xwork in read_xworks_dump(xworks_filename) 
					 for doc in process_xwork(xwork))
	write_solr_dump(solr_docs)

if __name__ == '__main__':
	main(sys.argv[1])
