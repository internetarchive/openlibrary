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
import copy
import itertools
import logging as Logging

import web

from .functions import massage_search_results, thing_to_doc
from .matchers import match_functions

logger = Logging.getLogger("openlibrary.importapi")

def search(params):
    params = params["doc"]
    matched_keys = run_matchers(params)
    filtered_keys = run_filter(matched_keys, params)
    return massage_search_results(list(filtered_keys))


def run_matchers(params):
    """
    Run all the matchers in the match_functions list and produce a list of keys which match the 
    """
    keys = []
    for i in match_functions:
        logger.debug("Running %s", i.__name__)
        keys.append(i(params))
    return itertools.chain.from_iterable(keys)

def run_filter(matched_keys, params):
    """
    Will check all the matched keys for the following conditions and
    emit only the ones that pass all of them.

    This function compensates for the permissiveness of the matchers.

    The rules are as follows

    1. All the fields provided in params should either be matched or
       missing in the record.
    2. In case of the title and author, if provided in params, it
          *should* match (absence is not acceptable).
       TODO: Don't create if title missing

    *match* needn't mean an exact match. This is especially true for
     publishers and such ('Dover publishers' and 'Dover' are
     equivalent).
    """

    def compare(i1, i2):
        """Compares `i1` to see if it matches `i2`
        according to the rules stated above.
        
        `i1` is originally the `thing` and `i2` the search parameters.
        """
        if i1 == i2: # Trivially the same
            return True

        if isinstance(i1, list) and isinstance(i2, list):
            # i2 should be a subset of i1.  Can't use plain old set
            # operations since we have to match recursively using
            # compare
            for i in i2:
                matched = False
                for j in i1:
                    if compare(i, j):
                        matched = True
                        break
                if not matched: # A match couldn't be found for atleast one element
                    logger.debug("Couldn't match %s in %s", i, i1)
                    return False
            return True

        if isinstance(i1, dict) and isinstance(i2, dict):
            # Every key in i2 should either be in i1 and matching
            #    OR
            # In case of the 'title' and 'authors', if it's there in
            # the search params, it *should* match.
            for k in i2:
                if k == "title" or k == "authors":
                    # Special case title and authors. Return False if not present in thing
                    # TODO: Convert author names to keys.
                    if k not in i1 or not compare(i1[k], i2[k]):
                        return False
                elif k in i1:
                    # Recursively match for other keys
                    if compare(i1[k], i2[k]):
                        pass
                    else:
                        return False
                else:
                    return False
            return True

        return False

    docs = (thing_to_doc(web.ctx.site.get(x)) for x in matched_keys)

    return itertools.imap(lambda x: web.ctx.site.get(x['key']), 
                          itertools.ifilter(lambda y: compare(y, params), docs))
