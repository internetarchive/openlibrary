"""
Filters used to check if a certain statistic should be recorded
"""
import re
import logging
l = logging.getLogger("openlibrary.stats_filters")

import web

def all(**params):
    "Returns true for all requests"
    return True

def url(**params):
    l.debug("Evaluate url '%s'"%web.ctx.path)
    if re.search(params['pattern'], web.ctx.path):
        return True
    else:
        return False
    


