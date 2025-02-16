"""
Filters used to check if a certain statistic should be recorded
"""

import logging
import re

logger = logging.getLogger("openlibrary.stats_filters")

import web

from infogami import config


def all(**params):
    "Returns true for all requests"
    return True


def url(**params):
    logger.debug("Evaluate url '%s'" % web.ctx.path)
    return bool(re.search(params["pattern"], web.ctx.path))


def loggedin(**kw):
    """Returns True if any user is logged in."""
    # Assuming that presence of cookie is an indication of logged-in user.
    # Avoiding validation or calling web.ctx.site.get_user() as they are expensive.
    return config.login_cookie_name in web.cookies()


def not_loggedin(**kw):
    """Returns True if no user is logged in."""
    return not loggedin()
