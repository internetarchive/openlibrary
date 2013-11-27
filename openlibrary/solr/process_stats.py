"""Script to process various stats collected by the system and load them into solr.

The loan stats are currently sorted in couchdb. Solr provides wonderful
faceting that allows us to build beautiful views of data.

This file provides all the functionality to take one loan stats record, 
query OL and archive.org for other related info like subjects, collections
etc. and massages that into a form that can be fed into solr.
"""
import sys
import web
import simplejson
import logging

from openlibrary.solr.solrwriter import SolrWriter

logger = logging.getLogger("openlibrary.solr")

def get_document(key):
    return web.ctx.site.get(key)

class LoanEntry(web.storage):
    @property
    def key(self):
        return self['_id']

    @property
    def book_key(self):
        return self['book']

    @property
    def book(self):
        return get_document(self['book'])

    def get_subjects(self, type="subject"):
        w = self.book.works[0]
        if w:
            return w.get_subject_links(type)
        else:
            return []

    @property
    def metadata(self):
        return self.book.get_ia_meta_fields() or {}

def process(data):
    doc = LoanEntry(data)
    solrdoc = {
        "key": doc.key,
        "type": "stats",
        "stat_type_s": "loan",
        "book_key_s": doc.book_key,
        "title": doc.book.title or "Untitled",
        "ia": doc.book.ocaid or None,
        "resource_type_s": doc.resource_type,
        "ia_collections_id": doc.metadata.get("collection", []),
        "sponsor_s": doc.metadata.get("sponsor"),
        "contributor_s": doc.metadata.get("contributor"),
        "start_time_dt": doc.t_start + "Z",
        "start_day_s":doc.t_start.split("T")[0],
    }

    def add_subjects(type):
        subjects = doc.get_subjects(type)
        solrdoc[type + '_key'] = [s.key for s in subjects]
        solrdoc[type + '_facet'] = [s.title for s in subjects]

    add_subjects("subject")
    add_subjects("place")
    add_subjects("people")
    return solrdoc

def read_events():
    for line in sys.stdin:
        doc = simplejson.loads(line.strip())
        yield doc

def main(*args):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    docs = read_events()
    if "--load" in args:
        update_solr(docs)
    else:
        for e in docs:
            result = process(e['doc'])
            print simplejson.dumps(result)

def update_solr(docs):
    solr = SolrWriter("localhost:8983")
    for doc in docs:
        solr.update(doc)
    solr.commit()

