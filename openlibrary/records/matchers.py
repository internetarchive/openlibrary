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
import logging as Logging

import web

logger = Logging.getLogger(__name__)

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

def match_tap_infogami(params):
    "Search infogami using title, author and publishers"
    return []

def match_tap_solr(params):
    "Search solr for works using title and author and narrow using publishers"
    return []


match_functions = [match_isbn,
                   match_tap_infogami,
                   match_tap_solr
                   ]



