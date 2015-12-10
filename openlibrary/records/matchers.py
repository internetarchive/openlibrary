"""
Matchers
========

This module contains a list of functions that are used to search for
records in the database.

Each function will receive a dictionary that contains the search
parameters. This shouldn't be modified (make a copy if you have to
modify it). It can do whatever kinds of searches it wants to and then
should return an iterable of keys of matched things.

The `match_functions` is a list of functions in order of running. To
reduce computation, it's a good idea to put the more accurately
matching ones which require less queries on the top (e.g. exact ISBN
searches etc.). Adding a new matcher means creating a new function and
then adding the function to this list.


"""

import copy
from collections import defaultdict
import logging as Logging

from infogami import config
from openlibrary.utils.solr import Solr
import web


logger = Logging.getLogger(__name__)


def get_works_solr():
    base_url = "http://%s/solr/works" % config.plugin_worksearch.get('solr')
    return Solr(base_url)

def get_authors_solr():
    base_url = "http://%s/solr/authors" % config.plugin_worksearch.get('author_solr')
    return Solr(base_url)


def match_isbn(params):
    "Search by ISBN for exact matches"
    if "isbn" in params.get("identifiers",{}):
        isbns = params["identifiers"]["isbn"]
        q = {
            'type':'/type/edition',
            'isbn_': [str(x) for x in isbns]
            }
        logger.debug("ISBN query : %s", q)
        ekeys = list(web.ctx.site.things(q))
        if ekeys:
            return ekeys
    return []

def match_identifiers(params):
    "Match by identifiers"
    print params
    counts = defaultdict(int)
    identifiers = copy.deepcopy(params.get("identifiers",{}))
    for i in ["oclc_numbers", "lccn", "ocaid"]:
        if i in identifiers:
            val = identifiers.pop(i)
            query = {'type':'/type/edition',
                     i : val}
            matches = web.ctx.site.things(query)
            for i in matches:
                counts[i] += 1
    for k,v in identifiers.iteritems(): # Rest of the identifiers
        print "Trying ", k , v
        query = {'type':'/type/edition',
                 'identifiers' : {k : v}}
        matches = web.ctx.site.things(query)
        for i in matches:
            counts[i] += 1

    return sorted(counts, key = counts.__getitem__, reverse = True)

def match_tap_infogami(params):
    "Search infogami using title, author and publishers"
    return []

def match_tap_solr(params):
    """Search solr for works using title and author and narrow using
    publishers.

    Note:
    This function is ugly and the idea is to contain ugliness here
    itself so that it doesn't leak into the rest of the library.
    
    """

    asolr = get_authors_solr()
    wsolr = get_works_solr()
    # First find author keys. (if present in query) (TODO: This could be improved)
    # if "authors" in params:
    #     q = 'name:(%s) OR alternate_names:(%s)' % (name, name)
    
    return []


match_functions = [match_isbn,
                   match_identifiers,
                   match_tap_infogami,
                   match_tap_solr
                   ]



