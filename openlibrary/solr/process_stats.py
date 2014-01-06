"""Script to process various stats collected by the system and load them into solr.

The loan stats are currently sorted in couchdb. Solr provides wonderful
faceting that allows us to build beautiful views of data.

This file provides all the functionality to take one loan stats record, 
query OL and archive.org for other related info like subjects, collections
etc. and massages that into a form that can be fed into solr.

How to run:

    ./scripts/openlibrary-server openlibrary.yml runmain openlibrary.solr.process_stats --load 

"""
import sys
import web
import simplejson
import logging
import os
import time

from infogami import config
from openlibrary.solr.solrwriter import SolrWriter
from ..core import inlibrary, ia, helpers as h
from ..core.loanstats import LoanStats

logger = logging.getLogger("openlibrary.solr")

@web.memoize
def get_db():
    return web.database(**web.config.db_parameters)

def get_document(key):
    return web.ctx.site.get(key)

def is_region(library):
    return bool(library.lending_region)

def get_region(library):
    if library.lending_region:
        return library.lending_region

    # Take column #3 from address. The available columns are:
    # name, street, city, state, ...        
    try:
        # Open library of Richmond is really rest of the world 
        if library.addresses and library.key != "/libraries/openlibrary_of_richmond":
            return library.addresses.split("|")[3]
    except IndexError:
        pass
    return "WORLD"

_libraries = None
def get_library(key):
    global _libraries
    if _libraries is None:
        _libraries = dict((lib.key, lib) for lib in inlibrary.get_libraries())
    return _libraries.get(key, None)

_ia_db = None
def get_ia_db():
    """Metadata API is slow. 
    Talk to archive.org database directly if it is specified in the configuration.
    """
    if not config.get("ia_db"):
        return
    global _ia_db
    if not _ia_db:
        settings = config.ia_db
        host = settings['host']
        db = settings['db']
        user = settings['user']
        pw = os.popen(settings['pw_file']).read().strip()
        _ia_db = web.database(dbn="postgres", host=host, db=db, user=user, pw=pw)
    return _ia_db

@web.memoize
def get_metadata(ia_id):
    if not ia_id:
        return {}
    db = get_ia_db()
    if db:        
        result = db.query("SELECT collection, sponsor, contributor FROM metadata WHERE identifier=$ia_id", vars=locals())
        meta = result and result[0] or {}
        if meta:
            meta['collection'] = meta['collection'].split(";")
    else:
        meta = ia.get_meta_xml(ia_id)
    return meta

class LoanEntry(web.storage):
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

    def get_author_keys(self):
        w = self.book and self.book.works and self.book.works[0]
        if w:
            return [a.key for a in w.get_authors()]
        else:
            return []

    @property
    def metadata(self):
        return get_metadata(self.book.ocaid)

    @property
    def library(self):  
        key = self.get("library")
        lib = key and get_library(key)
        if lib and not is_region(lib):
            return lib.key.split("/")[-1]

    @property
    def region(self):
        key = self.get("library")
        lib = key and get_library(key)
        if lib:
            region =  get_region(lib).lower().strip()
            # some regions are specified with multiple names.
            # maintaining this dict to collapse them into single entry.
            region_aliases = {"california": "ca"}
            return region_aliases.get(region, region)

def process(data):
    doc = LoanEntry(data)
    if not doc.book:
        logger.error("Book not found for %r. Ignoring this loan", doc['book'])
        return

    solrdoc = {
        "key": doc.key,
        "type": "stats",
        "stats_type_s": "loan",
        "book_key_s": doc.book_key,
        "author_keys_id": doc.get_author_keys(),
        "title": doc.book.title or "Untitled",
        "ia": doc.book.ocaid or None,
        "resource_type_s": doc.resource_type,
        "ia_collections_id": doc.metadata.get("collection", []),
        "sponsor_s": doc.metadata.get("sponsor"),
        "contributor_s": doc.metadata.get("contributor"),
        "library_s": doc.library,
        "region_s": doc.region,
        "start_time_dt": doc.t_start + "Z",
        "start_day_s":doc.t_start.split("T")[0],
    }

    if doc.get('t_end'):
        dt = h.parse_datetime(doc.t_end) - h.parse_datetime(doc.t_start)
        hours = dt.days * 24 + dt.seconds / 3600
        solrdoc['duration_hours_i'] = hours

    #last_updated = h.parse_datetime(doc.get('t_end') or doc.get('t_start'))
    solrdoc['last_updated_dt'] = (doc.get('t_end') or doc.get('t_start')) + 'Z'

    solrdoc['subject_key'] = []
    solrdoc['subject_facet'] = []
    def add_subjects(type):
        subjects = doc.get_subjects(type)
        if type == 'subject':
            system_subjects = ['protected_daisy', 'accessible_book', 'in_library', 'lending_library']
            subjects = [s for s in subjects if s.slug not in system_subjects]
        solrdoc['subject_key'] += [type+":"+s.slug for s in subjects]
        solrdoc['subject_facet'] += [type+":"+s.title for s in subjects]

    add_subjects("subject")
    add_subjects("place")
    add_subjects("person")
    add_subjects("time")

    year = doc.book.get_publish_year()
    if year:
        solrdoc['publish_year'] = year

    # Remove None values
    solrdoc = dict((k, v) for k, v in solrdoc.items() if v is not None)
    return solrdoc

def read_events():
    for line in sys.stdin:
        doc = simplejson.loads(line.strip())
        yield doc

def read_events_from_db(keys=None, day=None):
    if keys:
        result = get_db().query("SELECT key, json FROM stats WHERE key in $keys ORDER BY updated", vars=locals())
    elif day:
        last_updated = day
        result = get_db().query("SELECT key, json FROM stats WHERE updated >= $last_updated AND updated < $last_updated::timestamp + interval '1' day ORDER BY updated", vars=locals())
    else:
        last_updated = LoanStats().get_last_updated()
        result = get_db().query("SELECT key, json FROM stats WHERE updated > $last_updated ORDER BY updated", vars=locals())
    for row in result.list():
        doc = simplejson.loads(row.json)
        doc['key'] = row.key
        yield doc

def debug():
    """Prints debug info about solr.
    """

def add_events_to_solr(events):
    solrdocs = (process(e) for e in events)
    solrdocs = (doc for doc in solrdocs if doc) # ignore Nones
    update_solr(solrdocs)

def main(*args):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if "--load" in args:        
        docs = read_events()
        update_solr(docs)
    elif args and args[0] == "--load-from-db":
        events = read_events_from_db()
        add_events_to_solr(events)
    elif args and args[0] == "--load-keys":
        keys = args[1:]
        events = read_events_from_db(keys=keys)
        add_events_to_solr(events)
    elif args and args[0] == "--day":
        day = args[1]
        events = read_events_from_db(day=day)
        add_events_to_solr(events)
    elif args and args[0] == "--debug":
        debug()
    else:
        docs = read_events()
        # each doc is one row from couchdb view response when called with include_docs=True
        for e in docs:
            try:
                result = process(e['doc'])
                print simplejson.dumps(result)
            except Exception:
                logger.error("Failed to process %s", e['doc']['_id'], exc_info=True)

def fix_subject_key(doc, name, prefix):
    if name in doc:
        doc[name] = [v.replace(prefix, '') for v in doc[name]]

def update_solr(docs):
    solr = SolrWriter("localhost:8983")
    for doc in docs:
        # temp fix for handling already processed data
        doc = dict((k, v) for k, v in doc.items() if v is not None)
        if isinstance(doc.get("ia_collections_id"), str):
            doc['ia_collections_id'] = doc['ia_collections_id'].split(";")

        fix_subject_key(doc, 'subject_key', '/subjects/')
        fix_subject_key(doc, 'place_key', '/subjects/place:')
        fix_subject_key(doc, 'person_key', '/subjects/person:')
        fix_subject_key(doc, 'time_key', '/subjects/time:')

        system_subjects = ['subject:Protected DAISY', 'subject:Accessible book', 'subject:In library', 'subject:Lending library']
        doc['subject_facet'] = [s for s in doc['subject_facet'] if s not in system_subjects]

        solr.update(doc)
    solr.commit()
