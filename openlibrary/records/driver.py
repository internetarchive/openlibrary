"""
Low level import API
====================

The Low level import API functions has 2 stages.

1. Matchers 
-----------

The matchers are functions present in the ``matchers`` module and
exposed via the ``match_functions`` list. These are functions that try
to search for entries in the database that match the input criteria in
various ways. The results of all the matchings are chained into a
single iterable and returned.

The matching is done liberally. The idea is to not miss any
records. We might have extra records that are bad matches.

The idea is to isolate the ugliness and complexity of the searches
into a small set of functions inside a single module. The rest of the
API can be clean and understandable then.


2. Filter
---------

The filter is a function that consumes the output of the matchers and
discards any items that are bad matches. This narrows the list of
matches and then returns the list of good ones.


Finally, the list of matched keys are massaged into the proper output
expected from the search API and returned to the client.

"""
import itertools
import logging as Logging

from .functions import massage_search_results
from .matchers import match_functions

logger = Logging.getLogger("openlibrary.importapi")

def search(params):
    params = params["doc"]
    matched_keys = run_matchers(params)
    filtered_keys = run_filter(matched_keys)
    return massage_search_results(filtered_keys)


def run_matchers(params):    
    keys = []
    for i in match_functions:
        logger.debug("Running %s", i.__name__)
        keys.append(i(params))
    return itertools.chain.from_iterable(keys)

def run_filter(matched_keys):
    return list(matched_keys)


