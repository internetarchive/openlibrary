"""
Filters used to check if a certain statistic should be recorded
"""
import logging
l = logging.getLogger("openlibrary.stats_filters")

def all(ctx, params = {}):
    "Returns true for all requests"
    l.debug("Evaluate all")
    return True

def url(ctx, params = {}):
    l.debug("Evaluate url")
    return True
    


