"""
Filters used to check if a certain statistic should be recorded
"""
import re
import logging
l = logging.getLogger("openlibrary.stats_filters")

def all(ctx, params = {}):
    "Returns true for all requests"
    l.debug("Evaluate all")
    return True

def url(ctx, params = {}):
    l.debug("Evaluate url '%s'"%ctx.path)
    if re.search(params['pattern'], ctx.path):
        l.debug(" Matching URL")
        return True
    else:
        l.debug(" URL doesn't match")
        return False
    


